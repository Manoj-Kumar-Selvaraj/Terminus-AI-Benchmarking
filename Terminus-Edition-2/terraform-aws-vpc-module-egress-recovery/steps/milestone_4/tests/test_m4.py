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
        assert r.returncode == 0, r.stderr
        return json.loads(out.read_text())


class TestMilestone4:
    def test_flow_log_covers_all_subnets_with_scoped_policy(self):
        """Flow log must cover all subnets and avoid wildcard resources."""
        c = cfg()
        s = plan(c)
        fl = s["flow_log"]
        assert fl
        assert fl["traffic_type"] == "ALL"
        assert fl["destination"] == c["flow_log"]["destination"]
        assert set(fl["subnet_ids"]) == {x["id"] for x in s["subnets"]}
        assert fl["iam_policy"]["Resource"] != "*"
        assert "${interface-id}" in fl["log_format"]

    def test_resolver_sg_only_allows_dns_from_corporate_cidrs(self):
        """Resolver SG ingress must be TCP/UDP 53 from configured corporate CIDRs only."""
        c = cfg()
        s = plan(c)
        rules = s["resolver_security_group"]["ingress"]
        assert len(rules) == 2
        assert sorted(r["protocol"] for r in rules) == ["tcp", "udp"]
        assert all(
            r["from_port"] == 53
            and r["to_port"] == 53
            and r["cidr_blocks"] == c["resolver"]["allowed_cidrs"]
            and "0.0.0.0/0" not in r["cidr_blocks"]
            for r in rules
        )

    def test_audit_resources_preserve_outputs(self):
        """Audit resources must not remove the existing output contract."""
        s = plan(cfg())
        assert (
            s["outputs"]["private_app_route_table_ids"]
            and s["flow_log"]["id"].startswith("fl-")
            and s["resolver_security_group"]["id"].startswith("sg-")
        )

    def test_main_tf_labels_preserved(self):
        """main.tf resource labels must remain for compatibility."""
        text = (MODULE / "main.tf").read_text(encoding="utf-8")
        for label in [
            "aws_vpc",
            "aws_subnet",
            "aws_route_table",
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
            "private_app_route_table_ids",
            "isolated_data_route_table_ids",
        ]:
            assert key in text
