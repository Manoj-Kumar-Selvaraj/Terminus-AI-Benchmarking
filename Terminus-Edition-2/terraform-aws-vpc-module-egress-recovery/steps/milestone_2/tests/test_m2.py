import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "bin" / "vpcsim"
CFG = APP / "infra/envs/prod/vpc_config.json"
MODULE = APP / "infra/modules/vpc"

EXPECTED_LABELS = [
    "aws_vpc",
    "aws_subnet",
    "aws_route_table",
    "aws_vpc_endpoint",
    "aws_flow_log",
    "aws_security_group",
]
EXPECTED_OUTPUTS = [
    "vpc_id",
    "public_subnet_ids",
    "private_app_subnet_ids",
    "isolated_data_subnet_ids",
    "private_app_route_table_ids",
    "isolated_data_route_table_ids",
]


def cfg():
    return json.loads(CFG.read_text())


def run(cmd, c):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        r = subprocess.run(
            [
                str(SIM),
                cmd,
                "--config",
                str(cp),
                "--out",
                str(out),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return r, json.loads(out.read_text())


class TestMilestone2:
    def test_gateway_endpoints_only_attach_app_route_tables(self):
        """S3 and DynamoDB endpoints attach only to app route tables."""
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

    def test_all_tf_labels_preserved(self):
        """main.tf resource labels must remain for compatibility."""
        text = (MODULE / "main.tf").read_text(encoding="utf-8")
        for label in EXPECTED_LABELS:
            assert label in text

    def test_all_outputs_preserved(self):
        """outputs.tf keys must remain for downstream modules."""
        text = (MODULE / "outputs.tf").read_text(encoding="utf-8")
        for key in EXPECTED_OUTPUTS:
            assert key in text

    def test_apply_state_and_prior_state_flags_remain_compatible(self):
        """apply writes --state and plan accepts that file through --prior-state."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            config_path = td_path / "config.json"
            apply_out = td_path / "apply.json"
            state_path = td_path / "state.json"
            prior_out = td_path / "prior.json"
            config_path.write_text(json.dumps(cfg()))

            apply_result = subprocess.run(
                [
                    str(SIM),
                    "apply",
                    "--config",
                    str(config_path),
                    "--out",
                    str(apply_out),
                    "--state",
                    str(state_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert apply_result.returncode == 0, apply_result.stderr + apply_result.stdout
            persisted = json.loads(state_path.read_text())
            assert persisted["outputs"]["private_app_route_table_ids"]

            plan_result = subprocess.run(
                [
                    str(SIM),
                    "plan",
                    "--config",
                    str(config_path),
                    "--prior-state",
                    str(state_path),
                    "--out",
                    str(prior_out),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert plan_result.returncode == 0, plan_result.stderr + plan_result.stdout
            planned = json.loads(prior_out.read_text())
            assert (
                planned["outputs"]["private_app_route_table_ids"]
                == persisted["outputs"]["private_app_route_table_ids"]
            )
