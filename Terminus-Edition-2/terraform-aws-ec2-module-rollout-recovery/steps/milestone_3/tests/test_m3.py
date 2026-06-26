# ruff: noqa: E501, E701, E702
import copy
import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim"
CFG = APP / "infra/envs/prod/ec2_config.json"
FIELDS = ("manifest_version","ami_id","ami_owner_account_id","architecture","commit_sha","build_id","user_data_sha256")


def config():
    return json.loads(CFG.read_text())


def digest(artifact):
    return hashlib.sha256(json.dumps({k:artifact[k] for k in FIELDS},sort_keys=True,separators=(",",":")).encode()).hexdigest()


def next_release(cfg, suffix="19"):
    value = copy.deepcopy(cfg)
    artifact = value["release_artifact"]
    artifact.update({"ami_id":f"ami-0feed202606{suffix}","commit_sha":f"commit-{suffix}-abcdef","build_id":f"build-202606{suffix}.1","user_data_sha256":suffix[0]*64})
    value["ami_catalog"]["images"][artifact["ami_id"]] = {"owner_account_id":artifact["ami_owner_account_id"],"architecture":artifact["architecture"],"state":"available","deprecated":False}
    artifact["manifest_sha256"] = digest(artifact)
    return value


def run(command, cfg, prior=None, state=None, journal=None):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); cp=td/"c.json"; out=td/"o.json"; cp.write_text(json.dumps(cfg))
        args=[str(SIM),command,"--config",str(cp),"--out",str(out)]
        if prior is not None:
            pp=td/"p.json"; pp.write_text(json.dumps(prior)); args += ["--prior-state",str(pp)]
        if state is not None: args += ["--state",str(state)]
        if journal is not None: args += ["--journal",str(journal)]
        result=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return result,json.loads(out.read_text())


def baseline():
    cfg=config(); result,state=run("plan",cfg); assert result.returncode==0; return cfg,state


class TestMilestone3:
    def test_prior_release_network_and_placement_behavior_is_preserved(self):
        """Safe refresh retains immutable release, private placement, and scoped ingress behavior."""
        cfg, old = baseline(); new = next_release(cfg)
        result, state = run("plan", new, prior=old)
        assert result.returncode == 0
        assert state["launch_template"]["ami_id"] == new["release_artifact"]["ami_id"]
        assert all(not i["public_ip_associated"] for i in state["instances"])
        assert state["security_group"]["ingress"][0]["source_security_group_id"] == new["network"]["alb_security_group_id"]

    def test_passing_refresh_uses_ordered_pilot_then_wave_events(self):
        """A healthy release commits the pilot before ordered replacement waves."""
        cfg, old = baseline(); new=next_release(cfg)
        result,state=run("plan",new,prior=old); assert result.returncode==0
        refresh=state["autoscaling_group"]["instance_refresh"]
        events=[e["event"] for e in refresh["events"]]
        assert refresh["strategy"]=="pilot-then-wave" and refresh["status"]=="completed"
        assert events[:3]==["pilot_launched","pilot_healthy","pilot_committed"]
        assert events[-1]=="rollout_completed"
        assert events.count("wave_launched")==events.count("wave_healthy")==events.count("wave_committed")
        for launched,healthy,committed in zip([i for i,e in enumerate(events) if e=="wave_launched"],[i for i,e in enumerate(events) if e=="wave_healthy"],[i for i,e in enumerate(events) if e=="wave_committed"]):
            assert launched < healthy < committed

    def test_capacity_invariant_holds_at_every_refresh_event(self):
        """The event timeline never exceeds max unavailable or drops below the healthy floor."""
        cfg, old=baseline(); new=next_release(cfg); _,state=run("plan",new,prior=old)
        refresh=state["autoscaling_group"]["instance_refresh"]
        desired=new["asg"]["desired_capacity"]
        minimum=math.ceil((desired-new["asg"]["max_unavailable"])*100/desired)
        assert refresh["min_healthy_percentage"]==minimum
        assert all(e["unavailable"]<=1 and e["healthy_capacity"]>=desired-1 for e in refresh["events"])

    def test_failed_pilot_preserves_complete_previous_capacity(self):
        """Pilot failure rolls back without replacing or duplicating any old instance."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["candidate_health"]="fail_pilot"
        result,state=run("plan",new,prior=old); assert result.returncode==0
        refresh=state["autoscaling_group"]["instance_refresh"]
        assert refresh["status"]=="rolled_back"
        assert [i["id"] for i in state["instances"]]==[i["id"] for i in old["instances"]]
        assert [e["event"] for e in refresh["events"]]==["pilot_launched","pilot_unhealthy","previous_capacity_preserved"]

    def test_failed_wave_restores_complete_previous_capacity(self):
        """A later health failure still returns to the exact pre-rollout fleet."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["candidate_health"]="fail_wave"
        result,state=run("plan",new,prior=old); assert result.returncode==0
        refresh=state["autoscaling_group"]["instance_refresh"]
        assert refresh["status"]=="rolled_back"
        assert state["outputs"]["instance_ids"]==old["outputs"]["instance_ids"]
        assert [e["event"] for e in refresh["events"]]==[
            "pilot_launched",
            "pilot_healthy",
            "pilot_committed",
            "wave_launched",
            "wave_unhealthy",
            "previous_capacity_preserved",
        ]
        assert [e["seq"] for e in refresh["events"]]==list(range(1,7))
        assert refresh["events"][3]["wave"]==1 and refresh["events"][4]["wave"]==1

    def test_lost_response_commits_pilot_state_before_returning_error(self, tmp_path):
        """A lost response returns nonzero only after durable pilot progress is written."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        state_path=tmp_path/"state.json"; journal=tmp_path/"journal.jsonl"
        result,output=run("apply",new,prior=old,state=state_path,journal=journal)
        assert result.returncode==3 and state_path.exists()
        durable=json.loads(state_path.read_text())
        refresh=durable["autoscaling_group"]["instance_refresh"]
        assert output==durable and refresh["status"]=="in_progress" and refresh["completed_slots"]==[0]
        assert [e["event"] for e in refresh["events"]]==["pilot_launched","pilot_healthy","pilot_committed"]

    def test_restart_resumes_first_unfinished_slot_without_duplicates(self, tmp_path):
        """Retrying from committed pilot state completes remaining slots once."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        first_state=tmp_path/"first.json"; journal=tmp_path/"journal.jsonl"
        first,_=run("apply",new,prior=old,state=first_state,journal=journal); assert first.returncode==3
        prior=json.loads(first_state.read_text())
        second_state=tmp_path/"second.json"; second,done=run("apply",new,prior=prior,state=second_state,journal=journal)
        assert second.returncode==0
        refresh=done["autoscaling_group"]["instance_refresh"]
        assert refresh["status"]=="completed" and refresh["completed_slots"]==list(range(6))
        assert len(done["outputs"]["instance_ids"])==len(set(done["outputs"]["instance_ids"]))==6
        assert [e["event"] for e in refresh["events"]].count("pilot_committed")==1

    def test_operation_identity_is_stable_across_lost_response_resume(self, tmp_path):
        """The same source and target release retain one rollout operation identity."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        path=tmp_path/"state.json"; first,out=run("apply",new,prior=old,state=path); assert first.returncode==3
        operation=out["outputs"]["rollout_operation_id"]
        second,done=run("plan",new,prior=json.loads(path.read_text()))
        assert second.returncode==0 and done["outputs"]["rollout_operation_id"]==operation

    def test_operation_identity_changes_when_desired_capacity_changes(self):
        """Desired capacity is part of the rollout operation identity."""
        cfg,old=baseline(); new=next_release(cfg); result,state=run("plan",new,prior=old)
        assert result.returncode==0
        smaller=config(); smaller["asg"]["desired_capacity"]=5
        _,smaller_old=run("plan",smaller); smaller_new=next_release(smaller)
        changed,changed_state=run("plan",smaller_new,prior=smaller_old)
        assert changed.returncode==0
        assert changed_state["outputs"]["rollout_operation_id"]!=state["outputs"]["rollout_operation_id"]

    def test_stale_owner_cannot_resume_in_progress_rollout(self, tmp_path):
        """A different controller token is fenced from committed rollout state."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        path=tmp_path/"state.json"; first,_=run("apply",new,prior=old,state=path); assert first.returncode==3
        stale=copy.deepcopy(new); stale["rollout"]["owner_token"]="stale-controller"
        result,output=run("plan",stale,prior=json.loads(path.read_text()))
        assert result.returncode!=0 and "stale rollout owner" in output["error"]

    def test_target_release_cannot_change_mid_operation(self, tmp_path):
        """An in-progress operation rejects a second target manifest."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        path=tmp_path/"state.json"; first,_=run("apply",new,prior=old,state=path); assert first.returncode==3
        changed=next_release(new,"20")
        result,output=run("plan",changed,prior=json.loads(path.read_text()))
        assert result.returncode!=0 and "target release changed" in output["error"]

    def test_completed_rollout_replay_is_noop(self):
        """Replanning completed target state creates no second refresh operation."""
        cfg,old=baseline(); new=next_release(cfg); _,done=run("plan",new,prior=old)
        result,replayed=run("plan",new,prior=done); assert result.returncode==0
        assert replayed["outputs"]["instance_ids"]==done["outputs"]["instance_ids"]
        assert not any(a["action"]=="rolling_replace" for a in replayed["plan_actions"])
        assert replayed["autoscaling_group"]["instance_refresh"]["events"]==done["autoscaling_group"]["instance_refresh"]["events"]

    @pytest.mark.parametrize("desired",[5,7,9])
    def test_healthy_floor_is_correct_for_odd_capacities(self, desired):
        """Refresh boundaries are derived from desired capacity rather than a hardcoded fleet size."""
        cfg=config(); cfg["asg"]["desired_capacity"]=desired; cfg["asg"]["max_size"]=max(cfg["asg"]["max_size"],desired)
        _,old=run("plan",cfg); new=next_release(cfg); result,state=run("plan",new,prior=old)
        assert result.returncode==0
        refresh=state["autoscaling_group"]["instance_refresh"]
        assert refresh["min_healthy_percentage"]==math.ceil((desired-1)*100/desired)
        assert refresh["completed_slots"]==list(range(desired))
