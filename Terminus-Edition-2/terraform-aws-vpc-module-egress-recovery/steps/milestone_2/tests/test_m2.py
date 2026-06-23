import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/vpcsim.py"
CFG = APP / "infra/envs/prod/vpc_config.json"


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
    def test_gateway_endpoints_only_attach_app_route_tables(self):
        """S3 and DynamoDB endpoints must attach to all app route tables and no public/data tables."""
        r, s = run("plan", cfg())
        assert r.returncode == 0
        app = set(s["outputs"]["private_app_route_table_ids"])
        bad = {rt["id"] for rt in s["route_tables"] if rt["tier"] != "app"}
        for ep in s["gateway_endpoints"]:
            assert set(ep["route_table_ids"]) == app and not (
                set(ep["route_table_ids"]) & bad
            )

    def test_endpoint_policy_preserves_account_provenance(self):
        """Endpoint policies must retain account provenance and module tags."""
        r, s = run("plan", cfg())
        assert r.returncode == 0
        assert all(
            ep["policy"]["Statement"][0]["Condition"]["StringEquals"][
                "aws:PrincipalAccount"
            ]
            == "111122223333"
            and ep["tags"]["ManagedBy"] == "terraform-aws-vpc-module"
            for ep in s["gateway_endpoints"]
        )

    def test_unknown_endpoint_service_fails_closed(self):
        """Unsupported endpoint services must fail validation deterministically."""
        c = cfg()
        c["gateway_endpoints"] = [{"service": "sqs"}]
        r, o = run("validate", c)
        assert r.returncode != 0 and o["valid"] is False and "unsupported" in o["error"]
