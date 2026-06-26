# ruff: noqa: E501, E701, E702
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim.py"
CFG = APP / "infra/envs/prod/ec2_config.json"
MODULE = APP / "infra/modules/ec2/module.py"
MAIN_TF = APP / "infra/modules/ec2/main.tf"
OUTPUTS_TF = APP / "infra/modules/ec2/outputs.tf"
MIGRATIONS_TF = APP / "infra/modules/ec2/state_migrations.tf"
FIELDS = ("manifest_version","ami_id","ami_owner_account_id","architecture","commit_sha","build_id","user_data_sha256")
EXPECTED_MOVES = {
    ("aws_launch_template.payments", "aws_launch_template.this"),
    ("aws_autoscaling_group.payments", "aws_autoscaling_group.this"),
    ("aws_security_group.payments_instance", "aws_security_group.instance"),
    ("aws_iam_role.payments_instance", "aws_iam_role.instance"),
    ("aws_ebs_volume.payments_data", "aws_ebs_volume.data"),
    ("aws_volume_attachment.payments_data", "aws_volume_attachment.data"),
}


def config():
    return json.loads(CFG.read_text())


def digest(artifact):
    return hashlib.sha256(json.dumps({k:artifact[k] for k in FIELDS},sort_keys=True,separators=(",",":")).encode()).hexdigest()


def next_release(cfg,suffix="19"):
    value=copy.deepcopy(cfg); artifact=value["release_artifact"]
    artifact.update({"ami_id":f"ami-0feed202606{suffix}","commit_sha":f"commit-{suffix}-abcdef","build_id":f"build-202606{suffix}.1","user_data_sha256":suffix[0]*64})
    value["ami_catalog"]["images"][artifact["ami_id"]]={"owner_account_id":artifact["ami_owner_account_id"],"architecture":artifact["architecture"],"state":"available","deprecated":False}
    artifact["manifest_sha256"]=digest(artifact)
    return value


def run(command,cfg,prior=None,state=None,journal=None):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); cp=td/"c.json"; out=td/"o.json"; cp.write_text(json.dumps(cfg))
        args=[sys.executable,str(SIM),command,"--config",str(cp),"--out",str(out)]
        if prior is not None:
            pp=td/"p.json"; pp.write_text(json.dumps(prior)); args += ["--prior-state",str(pp)]
        if state is not None: args += ["--state",str(state)]
        if journal is not None: args += ["--journal",str(journal)]
        result=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return result,json.loads(out.read_text())


def baseline():
    cfg=config(); result,state=run("plan",cfg); assert result.returncode==0; return cfg,state


def legacy_state(state):
    old=copy.deepcopy(state); old["schema_version"]="ec2sim.aws.1"; old.pop("import_report",None)
    for instance in old["instances"]: instance.pop("slot",None)
    return old


class TestMilestone5:
    def test_prior_rollout_storage_and_network_recovery_is_preserved(self):
        """Final hardening retains prior release, private placement, refresh, and volume behavior."""
        cfg,old=baseline(); new=next_release(cfg); result,state=run("plan",new,prior=old)
        assert result.returncode==0
        assert state["autoscaling_group"]["instance_refresh"]["status"]=="completed"
        assert all(not i["public_ip_associated"] for i in state["instances"])
        assert len(state["ebs_volumes"])==len(state["instances"])
        assert all(v["encrypted"] and not v["orphaned"] for v in state["ebs_volumes"])

    def test_imdsv2_is_required_with_single_hop(self):
        """Launch-template metadata options disable IMDSv1 and container-style hop expansion."""
        cfg,state=baseline()
        assert state["launch_template"]["metadata_options"]=={"http_tokens":"required","http_endpoint":"enabled","http_put_response_hop_limit":1}

    def test_iam_policy_contains_exact_scoped_capabilities(self):
        """IAM actions, resources, and conditions match the documented control-plane needs."""
        cfg,state=baseline(); policy={stmt["Sid"]:stmt for stmt in state["iam_role"]["policy"]}
        assert set(policy)=={"SsmControlPlane","ReadReleaseArtifact","DecryptDataVolume","PublishPaymentsMetrics"}
        assert set(policy["SsmControlPlane"]["Action"])=={"ec2messages:GetMessages","ssm:UpdateInstanceInformation","ssmmessages:CreateControlChannel","ssmmessages:OpenControlChannel"}
        assert policy["SsmControlPlane"]["Resource"]=="*" and policy["SsmControlPlane"]["Condition"]=={"StringEquals":{"aws:ResourceAccount":cfg["account_id"]}}
        assert policy["ReadReleaseArtifact"]=={"Sid":"ReadReleaseArtifact","Action":["s3:GetObject"],"Resource":cfg["artifact_bucket_arn"]+"/*"}
        assert policy["DecryptDataVolume"]["Action"]==["kms:Decrypt"] and policy["DecryptDataVolume"]["Resource"]==[cfg["ebs_volumes"][0]["kms_key_arn"]]
        assert policy["PublishPaymentsMetrics"]["Condition"]=={"StringEquals":{"cloudwatch:namespace":cfg["metric_namespace"]}}

    def test_iam_has_no_wildcard_actions_and_only_conditioned_wildcard_resources(self):
        """Wildcard actions are forbidden and wildcard resources require documented conditions."""
        _,state=baseline()
        for statement in state["iam_role"]["policy"]:
            assert "*" not in statement["Action"]
            if statement["Resource"]=="*":
                assert statement.get("Condition")
                assert statement["Sid"] in {"SsmControlPlane","PublishPaymentsMetrics"}

    def test_state_migrations_declare_every_legacy_address(self):
        """Terraform moved blocks cover all legacy singleton and collection resources."""
        text=MIGRATIONS_TF.read_text()
        moves=set(re.findall(r"from\s*=\s*([^\s]+).*?to\s*=\s*([^\s]+)",text,re.S))
        assert moves==EXPECTED_MOVES

    def test_legacy_import_recovers_slots_and_preserves_instance_ids(self):
        """Legacy Slot tags reconstruct stable keys without replacing imported instances."""
        cfg,state=baseline(); imported=legacy_state(state)
        result,planned=run("plan",cfg,prior=imported); assert result.returncode==0
        assert planned["import_report"]["legacy_state"] is True
        assert {(m["from"],m["to"]) for m in planned["import_report"]["moved"]}==EXPECTED_MOVES
        assert planned["outputs"]["instance_ids"]==state["outputs"]["instance_ids"]
        assert [i["slot"] for i in planned["instances"]]==list(range(6))

    def test_legacy_instance_missing_slot_tag_fails_closed(self):
        """An imported instance without stable-key provenance is not guessed by list position."""
        cfg,state=baseline(); imported=legacy_state(state); imported["instances"][0]["tags"].pop("Slot")
        result,output=run("plan",cfg,prior=imported)
        assert result.returncode!=0 and "missing Slot tag" in output["error"]

    def test_unchanged_imported_state_has_no_replace_actions(self):
        """Unchanged imports produce no rolling or destructive replacement actions."""
        cfg,state=baseline(); result,planned=run("plan",cfg,prior=legacy_state(state)); assert result.returncode==0
        assert not any(a["action"] in {"rolling_replace","replace","delete"} for a in planned["plan_actions"])
        assert all(a["action"]=="no_op" for a in planned["plan_actions"])

    @pytest.mark.parametrize("field,value",[
        ("launch_template_version","manual-version"),
        ("public_ip_associated",True),
        ("subnet_id","subnet-manual"),
        ("security_group_id","sg-manual"),
    ])
    def test_manual_instance_drift_is_report_only(self,field,value):
        """Drift is surfaced with exact expected and actual values without replacement."""
        cfg,state=baseline(); state["instances"][0][field]=value
        result,planned=run("plan",cfg,prior=state); assert result.returncode==0
        entry=next(d for d in planned["drift_report"] if d["field"]==field)
        assert entry["instance_id"]==state["instances"][0]["id"] and entry["actual"]==value and entry["action"]=="report_only"
        assert planned["instances"][0][field]==value
        assert not any(a["action"]=="rolling_replace" for a in planned["plan_actions"])

    def test_multiple_drift_fields_are_reported_independently(self):
        """One instance can produce multiple audit entries without collapsing provenance."""
        cfg,state=baseline(); state["instances"][1]["public_ip_associated"]=True; state["instances"][1]["security_group_id"]="sg-bad"
        result,planned=run("plan",cfg,prior=state); assert result.returncode==0
        entries=[d for d in planned["drift_report"] if d["instance_id"]==state["instances"][1]["id"]]
        assert {e["field"] for e in entries}=={"public_ip_associated","security_group_id"}
        assert all(e["action"]=="report_only" for e in entries)

    def test_corrupt_final_journal_line_is_truncated_without_losing_valid_records(self,tmp_path):
        """Journal repair preserves every valid prefix record and removes only torn tail data."""
        cfg,state=baseline(); journal=tmp_path/"rollout.jsonl"
        valid=[{"seq":1,"event":"pilot_committed"},{"seq":2,"event":"wave_committed"}]
        journal.write_text("".join(json.dumps(x)+"\n" for x in valid)+"{\"seq\":3")
        result,planned=run("plan",cfg,prior=state,journal=journal); assert result.returncode==0
        assert planned["journal_repair"]=={"truncated_tail":True,"preserved_records":2}
        assert [json.loads(line) for line in journal.read_text().splitlines()]==valid

    def test_invalid_interior_journal_record_fails_closed(self,tmp_path):
        """Interior corruption cannot be discarded as if it were a torn final write."""
        cfg,state=baseline(); journal=tmp_path/"rollout.jsonl"
        journal.write_text('{"seq":1}\nnot-json\n{"seq":3}\n')
        result,output=run("plan",cfg,prior=state,journal=journal)
        assert result.returncode!=0 and "invalid interior journal record" in output["error"]

    def test_restart_reconciliation_of_in_progress_rollout_is_idempotent(self,tmp_path):
        """Durable pilot state resumes once and repeated reconciliation becomes a no-op."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        state_path=tmp_path/"state.json"; first,_=run("apply",new,prior=old,state=state_path); assert first.returncode==3
        partial=json.loads(state_path.read_text())
        second,done=run("plan",new,prior=partial); assert second.returncode==0 and done["autoscaling_group"]["instance_refresh"]["status"]=="completed"
        third,replayed=run("plan",new,prior=done); assert third.returncode==0
        assert replayed["outputs"]["instance_ids"]==done["outputs"]["instance_ids"]
        assert replayed["autoscaling_group"]["instance_refresh"]["events"]==done["autoscaling_group"]["instance_refresh"]["events"]

    def test_stale_restart_owner_remains_fenced(self,tmp_path):
        """Restart does not weaken operation ownership after committed pilot progress."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        path=tmp_path/"state.json"; first,_=run("apply",new,prior=old,state=path); assert first.returncode==3
        stale=copy.deepcopy(new); stale["rollout"]["owner_token"]="another-owner"
        result,output=run("plan",stale,prior=json.loads(path.read_text()))
        assert result.returncode!=0 and "stale rollout owner" in output["error"]

    def test_terraform_labels_outputs_and_source_integrity_are_preserved(self):
        """The repair keeps public module addresses and avoids hidden bypass controls."""
        main=MAIN_TF.read_text(); outputs=OUTPUTS_TF.read_text(); source=MODULE.read_text()
        for label in ["aws_launch_template\" \"this","aws_autoscaling_group\" \"this","aws_security_group\" \"instance","aws_iam_role\" \"instance","aws_ebs_volume\" \"data","aws_volume_attachment\" \"data"]:
            assert label in main
        for key in ["launch_template_id","launch_template_version","autoscaling_group_name","instance_ids","volume_ids","rollout_operation_id","drift_report"]:
            assert f'output "{key}"' in outputs
        assert "FEATURE_LEVEL" not in source and "skip_validation" not in source and "force_success" not in source
        assert "ami-0feed20260618" not in source and "subnet-app-a" not in source
