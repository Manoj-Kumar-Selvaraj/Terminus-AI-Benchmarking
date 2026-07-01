# ruff: noqa: E501, E701, E702
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim"
CFG = APP / "infra/envs/prod/ec2_config.json"
FIELDS = ("manifest_version","ami_id","ami_owner_account_id","architecture","commit_sha","build_id","user_data_sha256")


def config():
    return json.loads(CFG.read_text())


def run(cfg, prior=None):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); cp = td / "c.json"; out = td / "o.json"
        cp.write_text(json.dumps(cfg))
        args = [str(SIM), "plan", "--config", str(cp), "--out", str(out)]
        if prior is not None:
            pp = td / "p.json"; pp.write_text(json.dumps(prior)); args += ["--prior-state", str(pp)]
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result, json.loads(out.read_text())


def validate(cfg):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); cp = td / "c.json"; out = td / "o.json"
        cp.write_text(json.dumps(cfg))
        result = subprocess.run([str(SIM), "validate", "--config", str(cp), "--out", str(out)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result, json.loads(out.read_text())


def assert_integer_plan_action_slots(actions):
    for action in actions:
        assert isinstance(action["slot"], int), (
            f"slot must be int, got {type(action['slot'])}"
        )


class TestMilestone2:
    def test_release_identity_recovery_is_preserved(self):
        """Network repair keeps immutable release identity and provenance intact."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        artifact = cfg["release_artifact"]
        template = state["launch_template"]
        assert template["ami_id"] == artifact["ami_id"]
        assert template["architecture"] == artifact["architecture"]
        assert template["user_data_sha256"] == artifact["user_data_sha256"]
        assert template["provenance"] == {
            "commit_sha": artifact["commit_sha"],
            "build_id": artifact["build_id"],
            "manifest_sha256": artifact["manifest_sha256"],
        }
        assert state["release_identity"]["manifest_sha256"] == artifact["manifest_sha256"]
        assert all(
            instance["tags"]["ReleaseManifestSha256"] == artifact["manifest_sha256"]
            for instance in state["instances"]
        )

    def test_release_identity_remains_deterministic_under_config_reordering(self):
        """Milestone 2 preserves canonical release identity when input key order changes."""
        cfg = config()
        first_result, first = run(cfg)
        reordered = json.loads(json.dumps(cfg, sort_keys=True))
        reordered["release_artifact"] = dict(
            reversed(list(reordered["release_artifact"].items()))
        )
        second_result, second = run(reordered, prior=first)
        assert first_result.returncode == second_result.returncode == 0
        assert first["launch_template"]["version"] == second["launch_template"]["version"]
        assert first["outputs"]["instance_ids"] == second["outputs"]["instance_ids"]
        assert not any(action["action"] == "rolling_replace" for action in second["plan_actions"])

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
        """Capacity growth retains old placement and creates only the new logical slots."""
        cfg = config(); _, first = run(cfg)
        scaled = config(); scaled["asg"]["desired_capacity"] = 8
        result, second = run(scaled, prior=first)
        assert result.returncode == 0
        assert second["outputs"]["instance_ids"][:6] == first["outputs"]["instance_ids"]
        assert {i["slot"]: i["subnet_id"] for i in second["instances"] if i["slot"] < 6} == {
            i["slot"]: i["subnet_id"] for i in first["instances"]
        }
        assert [i["slot"] for i in second["instances"]] == list(range(8))
        assert len(second["plan_actions"]) == 8
        for action in second["plan_actions"]:
            assert isinstance(action["slot"], int), (
                f"slot must be int, got {type(action['slot'])}"
            )
        no_ops = [a for a in second["plan_actions"] if a["action"] == "no_op"]
        assert len(no_ops) == 6
        assert [{"slot": a["slot"], "instance_id": a["instance_id"]} for a in no_ops] == [
            {"slot": slot, "instance_id": first["instances"][slot]["id"]}
            for slot in range(6)
        ]
        assert_integer_plan_action_slots(second["plan_actions"])
        creates = [a for a in second["plan_actions"] if a["action"] == "create"]
        assert [{"slot": a["slot"], "instance_id": a["instance_id"]} for a in creates] == [
            {"slot": 6, "instance_id": second["instances"][6]["id"]},
            {"slot": 7, "instance_id": second["instances"][7]["id"]},
        ]

    def test_steady_state_replan_emits_no_op_actions(self):
        """Unchanged capacity replans emit no_op entries for every existing slot."""
        cfg = config()
        _, first = run(cfg)
        result, second = run(cfg, prior=first)
        assert result.returncode == 0
        no_ops = [a for a in second["plan_actions"] if a["action"] == "no_op"]
        assert len(no_ops) == 6
        assert [{"slot": a["slot"], "instance_id": a["instance_id"]} for a in no_ops] == [
            {"slot": slot, "instance_id": first["instances"][slot]["id"]}
            for slot in range(6)
        ]
        assert all("instance_id" in a for a in no_ops)
        assert_integer_plan_action_slots(second["plan_actions"])

    def test_scale_in_emits_typed_plan_actions(self):
        """Capacity reduction emits scale_in entries for removed slots."""
        cfg = config()
        _, first = run(cfg)
        shrunk = config()
        shrunk["asg"]["desired_capacity"] = 4
        result, third = run(shrunk, prior=first)
        assert result.returncode == 0
        scale_ins = [a for a in third["plan_actions"] if a["action"] == "scale_in"]
        assert len(scale_ins) == 2
        assert [{"slot": a["slot"], "instance_id": a["instance_id"]} for a in scale_ins] == [
            {"slot": 4, "instance_id": first["instances"][4]["id"]},
            {"slot": 5, "instance_id": first["instances"][5]["id"]},
        ]
        assert all("instance_id" in a for a in scale_ins)
        assert_integer_plan_action_slots(third["plan_actions"])

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
        cfg = config()
        cfg["placement"]["minimum_azs"] = 4
        result, output = validate(cfg)
        assert result.returncode != 0 and "at least 4" in output["error"]

    def test_ingress_is_exactly_alb_to_service_port(self):
        """The instance security group has one ALB-origin service rule and no admin CIDR."""
        cfg = config(); result, state = run(cfg)
        assert result.returncode == 0
        assert state["security_group"]["ingress"] == [{"protocol":"tcp","from_port":8080,"to_port":8080,"source_security_group_id":cfg["network"]["alb_security_group_id"]}]
        assert "0.0.0.0/0" not in json.dumps(state["security_group"])

    def test_egress_is_exactly_endpoints_and_resolver(self):
        """Egress sorts shuffled endpoint lists and retains only scoped resolver rules."""
        cfg = config()
        cfg["network"]["endpoint_prefix_lists"] = ["pl-ssm", "pl-logs", "pl-s3"]
        result, state = run(cfg)
        assert result.returncode == 0
        egress = state["security_group"]["egress"]
        assert len(egress) == 3
        endpoint = next(rule for rule in egress if rule["to_port"] == 443)
        assert endpoint == {
            "protocol": "tcp",
            "from_port": 443,
            "to_port": 443,
            "prefix_list_ids": sorted(cfg["network"]["endpoint_prefix_lists"]),
        }
        resolver_rules = sorted(
            [rule for rule in egress if rule["to_port"] == 53],
            key=lambda rule: rule["protocol"],
        )
        assert [rule["protocol"] for rule in resolver_rules] == ["tcp", "udp"]
        for rule in resolver_rules:
            assert rule["from_port"] == rule["to_port"] == 53
            resolver = rule.get("source_security_group_id") or rule.get("destination_security_group_id")
            assert resolver == cfg["network"]["resolver_security_group_id"]

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
        assert result.returncode != 0
        if field != "endpoint_prefix_lists" or value not in (["pl-s3","pl-s3"], ["pl-s3","bad"]):
            assert error in output["error"]

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
