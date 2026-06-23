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


def run(c, prior=None):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        cmd = [sys.executable, str(SIM), "plan", "--config", str(cp), "--out", str(out)]
        if prior:
            pp = Path(td) / "p.json"
            pp.write_text(json.dumps(prior))
            cmd += ["--prior-state", str(pp)]
        r = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return r, json.loads(out.read_text())


class TestMilestone3:
    def test_failed_candidate_rolls_back_without_capacity_drop(self):
        """Failed canary must keep previous instances and report rollback."""
        c = cfg()
        r, old = run(c)
        assert r.returncode == 0
        c2 = cfg()
        c2["release_artifact"]["ami_id"] = "ami-bad"
        c2["candidate_health"] = "failing"
        r2, s = run(c2, old)
        assert r2.returncode == 0
        ref = s["autoscaling_group"]["instance_refresh"]
        assert (
            ref["status"] == "rolled_back" and "kept_previous_capacity" in ref["events"]
        )
        assert [i["id"] for i in s["instances"]] == [i["id"] for i in old["instances"]]

    def test_passing_refresh_uses_canary_min_healthy(self):
        """Passing refresh must use canary strategy with >=90 percent healthy capacity."""
        r, s = run(cfg())
        assert r.returncode == 0
        ref = s["autoscaling_group"]["instance_refresh"]
        assert (
            ref["strategy"] == "canary-then-batch"
            and ref["min_healthy_percentage"] >= 90
            and ref["min_healthy_instances"] >= 5
        )

    def test_idempotent_rerun_no_duplicate_instances(self):
        """Rerun with prior state must not duplicate instance identities."""
        c = cfg()
        r, p = run(c)
        assert r.returncode == 0
        r2, s = run(c, p)
        ids = s["outputs"]["instance_ids"]
        assert (
            r2.returncode == 0
            and len(ids) == len(set(ids)) == c["asg"]["desired_capacity"]
        )
