import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "bin" / "vpcsim"
CFG = APP / "infra/envs/prod/vpc_config.json"
MODULE = APP / "infra/modules/vpc"


def cfg():
    return json.loads(CFG.read_text())


def run(c, prior=None):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        cmd = [str(SIM), "plan", "--config", str(cp), "--out", str(out)]
        if prior:
            pp = Path(td) / "p.json"
            pp.write_text(json.dumps(prior))
            cmd += ["--prior-state", str(pp)]
        r = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return r, json.loads(out.read_text())


class TestMilestone5:
    def test_unchanged_imported_state_has_no_replacements(self):
        """Unchanged imported state must not replace VPC or route tables."""
        r, p = run(cfg())
        assert r.returncode == 0
        r2, s = run(cfg(), p)
        assert r2.returncode == 0 and not [
            a for a in s["plan_actions"] if a.get("action") == "replace"
        ]

    def test_legacy_private_subnet_move_is_declared(self):
        """Legacy private subnet paths must be represented as moved resources."""
        legacy_subnets = [
            {
                "cidr": "10.42.10.0/24",
                "id": "legacy-a",
                "address": "module.vpc.aws_subnet.private[0]",
            },
            {
                "cidr": "10.42.11.0/24",
                "id": "legacy-b",
                "address": "module.vpc.aws_subnet.private[1]",
            },
            {
                "cidr": "10.42.12.0/24",
                "id": "legacy-c",
                "address": "module.vpc.aws_subnet.private[2]",
            },
        ]
        r, s = run(
            cfg(),
            {"vpc": {"cidr": "10.42.0.0/16"}, "subnets": legacy_subnets},
        )
        assert r.returncode == 0
        moved = [
            x
            for x in s["moved"] + s["plan_actions"]
            if x.get("action") == "moved"
        ]
        assert len(moved) >= len(legacy_subnets)
        app_by_cidr = {
            subnet["cidr"]: subnet["address"]
            for subnet in s["subnets"]
            if subnet["tier"] == "app"
        }
        for legacy in legacy_subnets:
            match = [m for m in moved if m.get("from") == legacy["address"]]
            assert len(match) == 1
            assert match[0]["to"] == app_by_cidr[legacy["cidr"]]

    def test_missing_same_az_nat_fails_closed(self):
        """App AZ without same-AZ NAT must fail instead of routing cross-AZ."""
        r_ok, _ = run(cfg())
        assert r_ok.returncode == 0
        c = cfg()
        c["nat_gateways"] = [n for n in c["nat_gateways"] if n["az"] != "us-east-1c"]
        r, o = run(c)
        assert r.returncode != 0
        assert "missing nat gateway" in o["error"]
        assert "us-east-1c" in o["error"]

    def test_main_tf_labels_preserved(self):
        """main.tf resource labels must remain for compatibility."""
        text = (MODULE / "main.tf").read_text(encoding="utf-8")
        for label in [
            "aws_vpc",
            "aws_subnet",
            "aws_route_table",
            "aws_vpc_endpoint",
            "aws_flow_log",
            "aws_security_group",
        ]:
            assert label in text

    def test_outputs_tf_keys_preserved(self):
        """outputs.tf keys must remain for downstream modules."""
        text = (MODULE / "outputs.tf").read_text(encoding="utf-8")
        for key in [
            "vpc_id",
            "public_subnet_ids",
            "private_app_subnet_ids",
            "isolated_data_subnet_ids",
        ]:
            assert key in text

    def test_apply_writes_state_file(self):
        """apply subcommand must persist state through --state."""
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            cp = Path(td) / "c.json"
            out = Path(td) / "o.json"
            cp.write_text(json.dumps(cfg()))
            r = subprocess.run(
                [
                    str(SIM),
                    "apply",
                    "--config",
                    str(cp),
                    "--out",
                    str(out),
                    "--state",
                    str(state_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert r.returncode == 0, r.stderr + r.stdout
            assert state_path.exists()

    def test_validate_accepts_valid_config(self):
        """validate subcommand must accept the prod fixture."""
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td) / "c.json"
            out = Path(td) / "o.json"
            cp.write_text(json.dumps(cfg()))
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
            assert json.loads(out.read_text())["valid"] is True

    def test_cumulative_recovery_preserves_routing_endpoints_and_audit(self):
        """Final module state must retain routing, endpoint, and audit behavior."""
        r, s = run(cfg())
        assert r.returncode == 0
        c = cfg()
        nats = {n["az"]: n["id"] for n in c["nat_gateways"]}
        for rt in s["route_tables"]:
            if rt["tier"] == "app":
                default = next(r for r in rt["routes"] if r["destination"] == "0.0.0.0/0")
                assert default["target"] == nats[rt["az"]]
            if rt["tier"] == "data":
                assert not any(r["destination"] == "0.0.0.0/0" for r in rt["routes"])
        app_rt = set(s["outputs"]["private_app_route_table_ids"])
        for ep in s["gateway_endpoints"]:
            assert set(ep["route_table_ids"]) == app_rt
        fl = s["flow_log"]
        assert fl
        assert set(fl["subnet_ids"]) == {subnet["id"] for subnet in s["subnets"]}
        policy = fl["iam_policy"]
        assert isinstance(policy.get("Action"), list) and policy["Action"]
        rules = s["resolver_security_group"]["ingress"]
        assert len(rules) == 2
        assert all(r["cidr_blocks"] == c["resolver"]["allowed_cidrs"] for r in rules)
