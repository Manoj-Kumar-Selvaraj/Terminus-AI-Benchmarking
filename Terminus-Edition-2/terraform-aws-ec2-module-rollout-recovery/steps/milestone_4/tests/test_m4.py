# ruff: noqa: E501, E701, E702
import copy
import hashlib
import json
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


def attachment_token(volume):
    payload={"volume_id":volume["id"],"instance_id":volume["attached_instance_id"],"generation":volume["attachment_generation"]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:24]


def next_release(cfg, suffix="19"):
    value=copy.deepcopy(cfg); artifact=value["release_artifact"]
    artifact.update({"ami_id":f"ami-0feed202606{suffix}","commit_sha":f"commit-{suffix}-abcdef","build_id":f"build-202606{suffix}.1","user_data_sha256":suffix[0]*64})
    value["ami_catalog"]["images"][artifact["ami_id"]]={"owner_account_id":artifact["ami_owner_account_id"],"architecture":artifact["architecture"],"state":"available","deprecated":False}
    artifact["manifest_sha256"]=digest(artifact)
    return value


def run(command,cfg,prior=None,state=None,journal=None):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); cp=td/"c.json"; out=td/"o.json"; cp.write_text(json.dumps(cfg))
        args=[str(SIM),command,"--config",str(cp),"--out",str(out)]
        if prior is not None:
            pp=td/"p.json"; pp.write_text(json.dumps(prior)); args += ["--prior-state",str(pp)]
        if state is not None: args += ["--state",str(state)]
        if journal is not None: args += ["--journal",str(journal)]
        result=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return result,json.loads(out.read_text())


def validate(cfg):
    return run("validate",cfg)


def baseline():
    cfg=config(); result,state=run("plan",cfg); assert result.returncode==0; return cfg,state


class TestMilestone4:
    def test_prior_release_network_and_refresh_behavior_is_preserved(self):
        """Storage recovery keeps private placement and pilot-then-wave rollout semantics."""
        cfg,old=baseline(); new=next_release(cfg); result,state=run("plan",new,prior=old)
        assert result.returncode==0
        assert all(not i["public_ip_associated"] for i in state["instances"])
        assert state["autoscaling_group"]["instance_refresh"]["status"]=="completed"
        assert state["launch_template"]["ami_id"]==new["release_artifact"]["ami_id"]

    def test_each_slot_has_one_encrypted_non_orphaned_volume_per_definition(self):
        """Volume cardinality and security match logical slots and configured definitions."""
        cfg,state=baseline()
        assert len(state["ebs_volumes"])==len(state["instances"])*len(cfg["ebs_volumes"])
        instances={i["slot"]:i for i in state["instances"]}
        for volume in state["ebs_volumes"]:
            assert volume["encrypted"] is True and volume["orphaned"] is False
            assert volume["delete_on_termination"] is False
            assert volume["kms_key_alias"]==cfg["ebs_volumes"][0]["kms_key_alias"]
            assert volume["attached_instance_id"]==instances[volume["slot"]]["id"]

    def test_volume_identity_is_stable_across_instance_replacement(self):
        """Logical volume IDs survive rollout even though transient instance IDs change."""
        cfg,old=baseline(); new=next_release(cfg); _,done=run("plan",new,prior=old)
        assert {v["id"] for v in old["ebs_volumes"]}=={v["id"] for v in done["ebs_volumes"]}
        assert old["outputs"]["instance_ids"]!=done["outputs"]["instance_ids"]

    def test_attachment_generation_increments_exactly_once_per_replacement(self):
        """Every moved volume receives one new fenced attachment generation."""
        cfg,old=baseline(); new=next_release(cfg); _,done=run("plan",new,prior=old)
        before={(v["slot"],v["logical_name"]):v for v in old["ebs_volumes"]}
        for volume in done["ebs_volumes"]:
            prior=before[(volume["slot"],volume["logical_name"])]
            assert volume["attachment_generation"]==prior["attachment_generation"]+1
            assert volume["attachment_token"]!=prior["attachment_token"]

    def test_attachment_token_uses_documented_canonical_inputs(self):
        """Attachment tokens are derived from volume id, instance id, and generation."""
        _,state=baseline()
        for volume in state["ebs_volumes"]:
            assert volume["attachment_token"]==attachment_token(volume)

    def test_lost_response_resume_does_not_double_increment_pilot_attachment(self,tmp_path):
        """The already committed pilot attachment is reused during restart."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["fault_point"]="after_pilot_commit_response_lost"
        path=tmp_path/"state.json"; journal=tmp_path/"journal.jsonl"
        first,partial=run("apply",new,prior=old,state=path,journal=journal); assert first.returncode==3
        pilot_partial=next(v for v in partial["ebs_volumes"] if v["slot"]==0)
        second,done=run("apply",new,prior=json.loads(path.read_text()),state=tmp_path/"done.json",journal=journal)
        assert second.returncode==0
        pilot_done=next(v for v in done["ebs_volumes"] if v["slot"]==0)
        assert pilot_done["attachment_generation"]==pilot_partial["attachment_generation"]==2
        assert pilot_done["attachment_token"]==pilot_partial["attachment_token"]

    def test_failed_pilot_preserves_all_previous_attachments(self):
        """Rollback leaves volume ownership, generations, and tokens unchanged."""
        cfg,old=baseline(); new=next_release(cfg); new["rollout"]["candidate_health"]="fail_pilot"
        result,state=run("plan",new,prior=old); assert result.returncode==0
        assert state["ebs_volumes"]==old["ebs_volumes"]

    @pytest.mark.parametrize("mutation,error",[
        (lambda c:c["ebs_volumes"][0].__setitem__("encrypted",False),"unencrypted"),
        (lambda c:c["ebs_volumes"][0].__setitem__("kms_key_alias",""),"kms_key_alias"),
        (lambda c:c["ebs_volumes"][0].__setitem__("kms_key_arn","arn:aws:kms:us-east-1:999900001111:key/wrong"),"outside configured account"),
        (lambda c:c["ebs_volumes"][0].__setitem__("delete_on_termination",True),"delete_on_termination false"),
    ])
    def test_unsafe_volume_definitions_fail_closed(self,mutation,error):
        """Encryption, key provenance, alias, and retention are mandatory."""
        cfg=config(); mutation(cfg); result,output=validate(cfg)
        assert result.returncode!=0 and error in output["error"]

    def test_duplicate_logical_volume_names_fail_closed(self):
        """Two definitions cannot claim the same slot-level volume identity."""
        cfg=config(); cfg["ebs_volumes"].append(copy.deepcopy(cfg["ebs_volumes"][0]))
        result,output=validate(cfg)
        assert result.returncode!=0 and "duplicate ebs logical_name" in output["error"]

    def test_prior_volume_attached_to_another_slot_fails_closed(self):
        """Attachment ownership mismatch is not auto-repaired destructively."""
        cfg,old=baseline()
        old["ebs_volumes"][0]["attached_instance_id"]=old["instances"][1]["id"]
        result,output=run("plan",cfg,prior=old)
        assert result.returncode!=0 and "slot ownership" in output["error"]

    def test_multiple_volume_definitions_remain_unique_per_slot(self):
        """Additional logical volumes produce stable independent identities and tokens."""
        cfg=config(); extra=copy.deepcopy(cfg["ebs_volumes"][0]); extra.update({"logical_name":"audit-data","size_gb":40,"kms_key_alias":"alias/payments-audit","kms_key_arn":"arn:aws:kms:us-east-1:111122223333:key/payments-audit"}); cfg["ebs_volumes"].append(extra)
        result,state=run("plan",cfg); assert result.returncode==0
        assert len(state["ebs_volumes"])==12
        assert len({v["id"] for v in state["ebs_volumes"]})==12
        assert all(len([v for v in state["ebs_volumes"] if v["slot"]==slot])==2 for slot in range(6))
        expected={item["logical_name"]:item for item in cfg["ebs_volumes"]}
        seen={(v["slot"],v["logical_name"]) for v in state["ebs_volumes"]}
        assert seen=={(slot,item["logical_name"]) for slot in range(6) for item in cfg["ebs_volumes"]}
        for volume in state["ebs_volumes"]:
            spec=expected[volume["logical_name"]]
            assert volume["encrypted"] is True and volume["orphaned"] is False
            assert volume["size_gb"]==spec["size_gb"]
            assert volume["kms_key_alias"]==spec["kms_key_alias"]
            assert volume["kms_key_arn"]==spec["kms_key_arn"]
            assert volume["tags"]=={"Application":cfg["app"],"Environment":cfg["environment"],"Slot":str(volume["slot"]),"VolumeRole":volume["logical_name"],"ManagedBy":"terraform-aws-ec2-module"}

    def test_volume_tags_and_ids_are_slot_based_not_instance_based(self):
        """Inventory provenance is stable and does not embed transient instance identity."""
        cfg,state=baseline()
        for volume in state["ebs_volumes"]:
            assert volume["tags"]=={"Application":cfg["app"],"Environment":cfg["environment"],"Slot":str(volume["slot"]),"VolumeRole":volume["logical_name"],"ManagedBy":"terraform-aws-ec2-module"}
            assert volume["attached_instance_id"] not in volume["id"]
