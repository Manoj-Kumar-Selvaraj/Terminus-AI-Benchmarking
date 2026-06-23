import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim.py"
CFG = APP / "infra/envs/prod/ec2_config.json"


def cfg():
    return json.loads(CFG.read_text())


def run(cmd, c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [sys.executable, str(SIM), cmd, "--config", str(cp), "--out", str(out)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return r, json.loads(out.read_text())


class TestMilestone4:
    def test_ebs_volumes_are_encrypted_tagged_attached(self):
        """Every instance must have non-orphaned encrypted KMS data volume."""
        c = cfg()
        r, s = run("plan", c)
        assert r.returncode == 0
        vols = s["ebs_volumes"]
        ids = {i["id"] for i in s["instances"]}
        assert len(vols) == len(ids)
        assert all(
            v["instance_id"] in ids
            and v["encrypted"]
            and v["kms_key_alias"] == "alias/payments-ebs"
            and not v["orphaned"]
            and v["tags"]["ManagedBy"] == "terraform-aws-ec2-module"
            for v in vols
        )

    def test_unencrypted_volume_fails_closed(self):
        """Unencrypted volume config must fail validation."""
        c = cfg()
        c["ebs_volumes"][0]["encrypted"] = False
        r, o = run("validate", c)
        assert r.returncode != 0 and "unencrypted" in o["error"]

    def test_data_volumes_not_delete_on_termination(self):
        """Stateful data volumes must not delete on instance termination."""
        r, s = run("plan", cfg())
        assert r.returncode == 0
        assert all(v["delete_on_termination"] is False for v in s["ebs_volumes"])
