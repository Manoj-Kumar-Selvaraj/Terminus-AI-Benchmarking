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


class TestMilestone2:
    def test_instances_are_private_and_spread(self):
        """Instances must stay in private app subnets with no public IP association."""
        c = cfg()
        r, s = run("plan", c)
        assert r.returncode == 0
        assert {i["subnet_id"] for i in s["instances"]} == {
            x["id"] for x in c["subnets"]
        }
        assert all(i["public_ip_associated"] is False for i in s["instances"])

    def test_security_group_allows_only_alb_service_ingress(self):
        """Ingress must be ALB SG on service port only, not public admin ingress."""
        c = cfg()
        r, s = run("plan", c)
        assert r.returncode == 0
        assert s["security_group"]["ingress"] == [
            {
                "protocol": "tcp",
                "from_port": 8080,
                "to_port": 8080,
                "source_security_group_id": c["alb_security_group_id"],
            }
        ]
        assert "0.0.0.0/0" not in json.dumps(s["security_group"])

    def test_public_subnet_input_fails_closed(self):
        """Public subnet inputs must be rejected."""
        c = cfg()
        c["subnets"][0]["tier"] = "public"
        r, o = run("validate", c)
        assert r.returncode != 0 and "private_app" in o["error"]
