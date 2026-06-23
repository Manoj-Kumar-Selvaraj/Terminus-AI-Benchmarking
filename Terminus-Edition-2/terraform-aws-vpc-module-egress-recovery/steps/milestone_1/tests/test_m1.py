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


def plan(c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [sys.executable, str(SIM), "plan", "--config", str(cp), "--out", str(out)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        return json.loads(out.read_text())


class TestMilestone1:
    def test_app_routes_use_same_az_nat(self):
        """App subnet default routes must target NAT gateways in the same AZ."""
        c = cfg()
        s = plan(c)
        n = {x["az"]: x["id"] for x in c["nat_gateways"]}
        assert all(
            next(r for r in rt["routes"] if r["destination"] == "0.0.0.0/0")["target"]
            == n[rt["az"]]
            for rt in s["route_tables"]
            if rt["tier"] == "app"
        )

    def test_data_subnets_remain_isolated(self):
        """Data route tables must not receive a default internet route."""
        s = plan(cfg())
        assert all(
            not any(r["destination"] == "0.0.0.0/0" for r in rt["routes"])
            for rt in s["route_tables"]
            if rt["tier"] == "data"
        )

    def test_outputs_and_tags_are_compatible(self):
        """Output keys and subnet tagging must stay compatible."""
        s = plan(cfg())
        keys = {
            "vpc_id",
            "public_subnet_ids",
            "private_app_subnet_ids",
            "isolated_data_subnet_ids",
            "private_app_route_table_ids",
            "isolated_data_route_table_ids",
        }
        assert keys <= set(s["outputs"])
        assert all(
            x["tags"].get("Name") and x["tags"].get("Tier") for x in s["subnets"]
        )
