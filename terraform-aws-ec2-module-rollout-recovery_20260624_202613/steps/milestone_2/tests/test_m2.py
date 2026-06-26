# ruff: noqa: E501, E701, E702
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim.py"
CFG = APP / "infra/envs/prod/ec2_config.json"
FIELDS = ("manifest_version","ami_id","ami_owner_account_id","architecture","commit_sha","build_id","user_data_sha256")


def config():
    return json.loads(CFG.read_text())


def run(cfg, prior=None):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); cp = td / "c.json"; out = td / "o.json"
        cp.write_text(json.dumps(cfg))
        args = [sys.executable, str(SIM), "plan", "--config", str(cp), "--out", str(out)]
        if prior is not None:
            pp = td / "p.json"; pp.write_text(json.dumps(prior)); args += ["--prior-state", str(pp)]
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result, json.loads(out.read_text())


def validate(cfg):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); cp = td / "c.json"; out = td / "o.json"
        cp.write_text(json.dumps(cfg))
        result = subprocess.run([sys.executable, str(SIM), "validate", "--config", str(cp), "--out", str(out)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result, json.loads(out.read_text())


class TestMilestone2:
    def test_release_identity_recovery_is_preserved(self):
        """Network repair keeps immutable release identity and provenance intact."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        artifact = cfg["release_artifact"]
        assert state["launch_template"]["ami_id"] == artifact["ami_id"]
        assert state["launch_template"]["provenance"]["manifest_sha256"] == artifact["manifest_sha256"]

    def test_instances_are_private_and_balanced_across_eligible_azs(self):
        """All capacity is private and zone counts differ by no more than one."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        eligible = {s["id"] for s in cfg["placement"]["subnets"]}
        assert all(not i["public_ip_associated"] and i["subnet_id"] in eligible for i in state["instances"])
        counts = {}
        for instance in state["instances"]:
            counts[instance["az"]] = counts.get(instance["az"], 0) + 1
        assert set(counts) == {s["az"] for s in cfg["placement"]["subnets"]}
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_subnet_input_reordering_preserves_slot_placement(self):
        """Placement keys by stable AZ identity rather than list position."""
        cfg = config(); _, first = run(cfg)
        reordered = config(); reordered["placement"]["subnets"].reverse()
        result, second = run(reordered, prior=first)
        assert result.returncode == 0
        assert {i["slot"]: i["subnet_id"] for i in first["instances"]} == {i["slot"]: i["subnet_id"] for i in second["instances"]}
        assert first["outputs"]["instance_ids"] == second["outputs"]["instance_ids"]

    def test_az_expansion_does_not_move_existing_slots(self):
        """Adding an eligible AZ preserves existing slot-to-subnet assignments."""
        cfg = config(); _, first = run(cfg)
        expanded = config()
        expanded["placement"]["subnets"].append({"id":"subnet-app-d","az":"us-east-1d","tier":"private_app","account_id":expanded["account_id"]})
        result, second = run(expanded, prior=first)
        assert result.returncode == 0
        assert {i["slot"]: i["subnet_id"] for i in first["instances"]} == {i["slot"]: i["subnet_id"] for i in second["instances"]}

    def test_scale_out_adds_only_new_logical_slots(self):
        """Capacity growth retains old identities and creates only newly required slots."""
        cfg = config(); _, first = run(cfg)
        scaled = config(); scaled["asg"]["desired_capacity"] = 8
        result, second = run(scaled, prior=first)
        assert result.returncode == 0
        assert second["outputs"]["instance_ids"][:6] == first["outputs"]["instance_ids"]
        assert [i["slot"] for i in second["instances"]] == list(range(8))
        assert sum(a["action"] == "create" for a in second["plan_actions"]) == 2

    @pytest.mark.parametrize("mutation,error", [
        (lambda c: c["placement"]["subnets"].__setitem__(1, {**c["placement"]["subnets"][1], "id": c["placement"]["subnets"][0]["id"]}), "duplicate subnet"),
        (lambda c: c["placement"]["subnets"].__setitem__(1, {**c["placement"]["subnets"][1], "az": c["placement"]["subnets"][0]["az"]}), "duplicate availability"),
        (lambda c: c["placement"]["subnets"][0].__setitem__("tier", "public"), "private_app"),
        (lambda c: c["placement"]["subnets"][0].__setitem__("account_id", "999900001111"), "configured account"),
    ])
    def test_invalid_subnet_provenance_fails_closed(self, mutation, error):
        """Duplicate, public, cross-account, and duplicate-AZ subnet inputs are rejected."""
        cfg = config(); mutation(cfg); result, output = validate(cfg)
        assert result.returncode != 0 and error in output["error"]

    def test_minimum_az_requirement_fails_closed(self):
        """Removing an availability zone cannot silently weaken fleet resilience."""
        cfg = config(); cfg["placement"]["subnets"] = cfg["placement"]["subnets"][:2]
        result, output = validate(cfg)
        assert result.returncode != 0 and "at least 3" in output["error"]

    def test_ingress_is_exactly_alb_to_service_port(self):
        """The instance security group has one ALB-origin service rule and no admin CIDR."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        assert state["security_group"]["ingress"] == [{"protocol":"tcp","from_port":8080,"to_port":8080,"source_security_group_id":cfg["network"]["alb_security_group_id"]}]
        assert "0.0.0.0/0" not in json.dumps(state["security_group"])

    def test_egress_is_exactly_endpoints_and_resolver(self):
        """Egress contains scoped HTTPS endpoints plus TCP and UDP resolver rules only."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        assert state["security_group"]["egress"] == [
            {"protocol":"tcp","from_port":443,"to_port":443,"prefix_list_ids":sorted(cfg["network"]["endpoint_prefix_lists"])},
            {"protocol":"udp","from_port":53,"to_port":53,"source_security_group_id":cfg["network"]["resolver_security_group_id"]},
            {"protocol":"tcp","from_port":53,"to_port":53,"source_security_group_id":cfg["network"]["resolver_security_group_id"]},
        ]

    @pytest.mark.parametrize("field,value,error", [
        ("alb_security_group_id", "not-a-sg", "alb_security_group_id"),
        ("resolver_security_group_id", "resolver", "resolver_security_group_id"),
        ("endpoint_prefix_lists", [], "endpoint_prefix_lists is required"),
        ("endpoint_prefix_lists", ["pl-s3","pl-s3"], "duplicates"),
        ("endpoint_prefix_lists", ["pl-s3","bad"], "start with pl-"),
    ])
    def test_malformed_network_identifiers_fail_closed(self, field, value, error):
        """Malformed or ambiguous network identifiers are rejected before rendering."""
        cfg = config(); cfg["network"][field] = value
        result, output = validate(cfg)
        assert result.returncode != 0 and error in output["error"]

    def test_configured_service_port_is_preserved(self):
        """A non-default valid service port changes ingress without broadening sources."""
        cfg = config(); cfg["service_port"] = 8443
        result, state = run(cfg)
        assert result.returncode == 0
        rule = state["security_group"]["ingress"][0]
        assert rule["from_port"] == rule["to_port"] == 8443
        assert rule["source_security_group_id"] == cfg["network"]["alb_security_group_id"]

    @pytest.mark.parametrize("port", [0, -1, 70000, "http"])
    def test_invalid_service_port_fails_closed(self, port):
        """Malformed or out-of-range service ports are rejected before rendering."""
        cfg = config(); cfg["service_port"] = port
        result, output = validate(cfg)
        assert result.returncode != 0 and "service_port" in output["error"]
