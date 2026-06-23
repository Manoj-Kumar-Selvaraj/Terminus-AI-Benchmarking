import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/vpcsim.py"
CFG = APP / "infra/envs/prod/vpc_config.json"
MODULE = APP / "infra/modules/vpc"


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
        r, s = run(
            cfg(),
            {
                "vpc": {"cidr": "10.42.0.0/16"},
                "subnets": [
                    {
                        "cidr": "10.42.10.0/24",
                        "id": "legacy",
                        "address": "module.vpc.aws_subnet.private[0]",
                    }
                ],
            },
        )
        assert r.returncode == 0
        moved = [
            x
            for x in s["moved"] + s["plan_actions"]
            if x.get("action") == "moved"
        ]
        assert any(
            "private" in m.get("from", "") and "app" in m.get("to", "") for m in moved
        )

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
