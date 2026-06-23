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


class TestMilestone5:
    def test_imdsv2_required(self):
        """Launch template metadata options must require IMDSv2 with hop limit 1."""
        r, s = run(cfg())
        assert r.returncode == 0
        m = s["launch_template"]["metadata_options"]
        assert m["http_tokens"] == "required" and m["http_put_response_hop_limit"] == 1

    def test_iam_policy_is_scoped_not_admin_wildcard(self):
        """IAM policy must include SSM/artifact/KMS/metrics permissions without wildcard admin action."""
        r, s = run(cfg())
        assert r.returncode == 0
        p = json.dumps(s["iam_role"]["policy"])
        assert (
            '"Action": ["*"]' not in p
            and "s3:GetObject" in p
            and "kms:Decrypt" in p
            and "cloudwatch:PutMetricData" in p
            and "ssm:UpdateInstanceInformation" in p
        )

    def test_drift_report_is_report_only(self):
        """Old launch-template drift must be reported without replacement side effects."""
        c = cfg()
        r, p = run(c)
        assert r.returncode == 0
        p["instances"][0]["launch_template_version"] = "manual-old-version"
        r2, s = run(c, p)
        assert r2.returncode == 0
        assert (
            s["drift_report"]
            and s["drift_report"][0]["action"] == "report_only"
            and len(s["instances"]) == c["asg"]["desired_capacity"]
        )
