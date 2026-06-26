import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "bin" / "vpcsim"
CFG = APP / "infra/envs/prod/vpc_config.json"


def cfg():
    return json.loads(CFG.read_text())


def two_az_config():
    return {
        "environment": "test",
        "account_id": "111122223333",
        "vpc_cidr": "10.0.0.0/16",
        "availability_zones": ["us-west-2a", "us-west-2b"],
        "internet_gateway_id": "igw-test",
        "subnets": [
            {
                "name": "test-public-a",
                "tier": "public",
                "az": "us-west-2a",
                "cidr": "10.0.0.0/24",
            },
            {
                "name": "test-public-b",
                "tier": "public",
                "az": "us-west-2b",
                "cidr": "10.0.1.0/24",
            },
            {
                "name": "test-app-a",
                "tier": "app",
                "az": "us-west-2a",
                "cidr": "10.0.10.0/24",
            },
            {
                "name": "test-app-b",
                "tier": "app",
                "az": "us-west-2b",
                "cidr": "10.0.11.0/24",
            },
            {
                "name": "test-data-a",
                "tier": "data",
                "az": "us-west-2a",
                "cidr": "10.0.20.0/24",
            },
            {
                "name": "test-data-b",
                "tier": "data",
                "az": "us-west-2b",
                "cidr": "10.0.21.0/24",
            },
        ],
        "nat_gateways": [
            {"id": "nat-test-a", "az": "us-west-2a"},
            {"id": "nat-test-b", "az": "us-west-2b"},
        ],
        "gateway_endpoints": [{"service": "s3"}, {"service": "dynamodb"}],
    }


def assert_same_az_app_routes(c, s):
    n = {x["az"]: x["id"] for x in c["nat_gateways"]}
    assert all(
        next(r for r in rt["routes"] if r["destination"] == "0.0.0.0/0")["target"]
        == n[rt["az"]]
        for rt in s["route_tables"]
        if rt["tier"] == "app"
    )


def plan(c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [
                str(SIM),
                "plan",
                "--config",
                str(cp),
                "--out",
                str(out),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        return json.loads(out.read_text())


def apply(c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        state = Path(td) / "state.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [
                str(SIM),
                "apply",
                "--config",
                str(cp),
                "--out",
                str(out),
                "--state",
                str(state),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert state.exists()
        return json.loads(out.read_text())


def validate(c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [
                str(SIM),
                "validate",
                "--config",
                str(cp),
                "--out",
                str(out),
            ],
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
        assert_same_az_app_routes(c, s)

    def test_app_routes_2az_config(self):
        """Same-AZ NAT routing must generalize beyond the prod 3-AZ fixture."""
        c = two_az_config()
        s = plan(c)
        assert_same_az_app_routes(c, s)

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

    def test_apply_and_validate_still_work(self):
        """apply and validate subcommands remain compatible with the repaired module."""
        c = cfg()
        s = apply(c)
        assert s["outputs"]["vpc_id"]
        v = validate(c)
        assert v["valid"] is True
