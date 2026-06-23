# ruff: noqa: E501
import json
import sys
from pathlib import Path

APP = Path("/app")
sys.path.insert(0, str(APP / "scripts"))
from inspect_network_contract import build_summary  # noqa: E402


def summary():
    return build_summary(APP)


def read_json(rel):
    return json.loads((APP / rel).read_text(encoding="utf-8"))


def assert_fixtures_not_rewritten():
    state = read_json("fixtures/state_before_refactor.json")
    assert state["environment"] == "staging"
    assert state["vpc"]["id"] == "vpc-staging-01"
    assert state["vpc"]["cidr_block"] == "10.42.0.0/16"
    assert state["subnets"]["private-a"]["cidr_block"] == "10.42.16.0/20"
    assert state["subnets"]["private-b"]["cidr_block"] == "10.42.32.0/20"
    expected = read_json("fixtures/expected_private_route_tables.json")
    assert expected["private_route_table_ids"] == ["rtb-private-a", "rtb-private-b"]
    allowed = read_json("fixtures/allowed_endpoint_sources.json")
    assert "0.0.0.0/0" not in allowed["allowed_cidr_blocks"]
    assert "::/0" not in allowed.get("allowed_cidr_blocks", [])


def assert_core_module_present():
    for rel in [
        "modules/network/main.tf",
        "modules/network/routes.tf",
        "modules/network/endpoints.tf",
        "modules/network/security_groups.tf",
        "modules/network/outputs.tf",
        "modules/network/moved.tf",
    ]:
        path = APP / rel
        assert path.exists(), f"missing required module file {rel}"
    module_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((APP / "modules/network").glob("*.tf")))
    for resource_name in [
        'resource "aws_vpc" "this"',
        'resource "aws_subnet" "this"',
        'resource "aws_route_table" "this"',
        'resource "aws_vpc_endpoint" "gateway"',
        'resource "aws_vpc_endpoint" "interface"',
        'resource "aws_security_group" "endpoint"',
    ]:
        assert resource_name in module_text, f"module was reduced or bypassed; missing {resource_name}"


def assert_m1_contract(s):
    assert_fixtures_not_rewritten()
    assert_core_module_present()
    locals_map = s["locals"]
    inventory = locals_map["network_inventory"]
    state = read_json("fixtures/state_before_refactor.json")
    expected = s["expected_routes"]

    assert inventory["environment"] == state["environment"] == "staging"
    assert inventory["vpc"]["id"] == state["vpc"]["id"]
    assert inventory["vpc"]["cidr_block"] == state["vpc"]["cidr_block"]

    for key, expected_subnet in state["subnets"].items():
        current = inventory["subnets"].get(key)
        assert current is not None, f"missing stable subnet key {key}"
        for attr in ["id", "cidr_block", "az", "tier"]:
            assert current[attr] == expected_subnet[attr], f"subnet {key} changed {attr}"

    assert sorted(s["private_route_table_ids"]) == expected["private_route_table_ids"]
    assert sorted(s["public_route_table_ids"]) == expected["public_route_table_ids"]

    assoc = {item["subnet_id"]: item for item in s["association_details"]}
    assert set(assoc) == set(expected["private_subnet_to_route_table_id"]) | set(expected["public_subnet_to_route_table_id"])
    for subnet_id, route_table_id in expected["private_subnet_to_route_table_id"].items():
        item = assoc[subnet_id]
        assert item["subnet_tier"] == "private"
        assert item["route_table_tier"] == "private", f"{subnet_id} associated to non-private route table"
        assert item["route_table_id"] == route_table_id
    for subnet_id, route_table_id in expected["public_subnet_to_route_table_id"].items():
        item = assoc[subnet_id]
        assert item["subnet_tier"] == "public"
        assert item["route_table_tier"] == "public", f"{subnet_id} associated to non-public route table"
        assert item["route_table_id"] == route_table_id

    private_routes = locals_map["private_default_routes"]
    routes_by_rt = {route["route_table_id"]: route for route in private_routes.values()}
    assert set(routes_by_rt) == set(expected["private_route_table_ids"]), "NAT default routes must exist only on private route tables"
    for route_table_id, nat_id in expected["nat_by_private_route_table_id"].items():
        route = routes_by_rt[route_table_id]
        assert route["destination_cidr_block"] == "0.0.0.0/0"
        assert route["nat_gateway_id"] == nat_id
    assert not (set(routes_by_rt) & set(expected["public_route_table_ids"])), "public route table has private NAT route"

    destructive = [r for r in s["protected_replacement_risks"] if r["resource_type"] not in {"migration"}]
    assert destructive == [], destructive


def assert_m2_contract(s):
    assert_m1_contract(s)
    expected_private_ids = set(s["expected_routes"]["private_route_table_ids"])
    expected_public_ids = set(s["expected_routes"]["public_route_table_ids"])
    endpoints = s["locals"].get("gateway_vpc_endpoints", {})
    required = set(s["allowed_sources"]["required_gateway_endpoints"])
    assert required <= set(endpoints), f"missing required gateway endpoints: {required - set(endpoints)}"
    for name in sorted(required):
        endpoint = endpoints[name]
        assert endpoint["vpc_endpoint_type"] == "Gateway"
        attached = set(endpoint.get("route_table_ids", []))
        assert attached == expected_private_ids, f"{name} endpoint must attach exactly to private route tables"
        assert not (attached & expected_public_ids), f"{name} endpoint is attached to a public route table"
        assert endpoint.get("id"), f"{name} endpoint ID must be preserved"


def assert_m3_contract(s):
    assert_m2_contract(s)
    allowed = s["allowed_sources"]
    private_subnets = set(s["private_subnet_ids"])
    public_subnets = set(s["public_subnet_ids"])
    endpoints = s["interface_endpoints"]
    required = set(allowed["required_interface_endpoints"])
    assert required <= set(endpoints), f"missing interface endpoints: {required - set(endpoints)}"
    for name in sorted(required):
        endpoint = endpoints[name]
        assert endpoint["vpc_endpoint_type"] == "Interface"
        attached = set(endpoint.get("subnet_ids", []))
        assert attached, f"{name} has no subnet placement"
        assert attached <= private_subnets, f"{name} has non-private subnet placement: {attached - private_subnets}"
        assert not (attached & public_subnets), f"{name} is attached to public subnets"
        assert endpoint.get("private_dns_enabled") is True, f"{name} private DNS must be enabled"
        assert "sg-vpce-staging" in endpoint.get("security_group_ids", []), f"{name} must use the shared endpoint SG"

    rules = s["endpoint_security_group_rules"].get("ingress", [])
    assert rules, "endpoint SG must retain least-privilege ingress rules"
    allowed_sgs = set(allowed["allowed_security_group_ids"])
    allowed_cidrs = set(allowed["allowed_cidr_blocks"])
    for rule in rules:
        assert rule.get("protocol") in {"tcp", "-1"}
        assert rule.get("from_port") == 443 and rule.get("to_port") == 443, "endpoint ingress should be HTTPS only"
        cidrs = set(rule.get("cidr_blocks", []))
        ipv6 = set(rule.get("ipv6_cidr_blocks", []))
        sgs = set(rule.get("source_security_group_ids", []))
        assert "0.0.0.0/0" not in cidrs
        assert "::/0" not in ipv6
        assert cidrs <= allowed_cidrs, f"unapproved CIDR sources: {cidrs - allowed_cidrs}"
        assert sgs <= allowed_sgs, f"unapproved SG sources: {sgs - allowed_sgs}"
        assert cidrs or sgs, "ingress rule must name a documented source"


def assert_m4_contract(s):
    assert_m3_contract(s)
    expected = s["expected_outputs"]
    outputs = s["module_output_contract"]
    blocks = set(s["output_blocks"])
    for name, expected_value in expected.items():
        assert name in outputs, f"missing legacy output contract {name}"
        assert name in blocks, f"missing Terraform output block {name}"
        item = outputs[name]
        assert "shape" in item and "value" in item, f"output {name} must record shape and value"
        assert item["value"] == expected_value, f"output {name} points to the wrong semantic resource"
    assert "network" in outputs and "network" in blocks, "new aggregate output may remain but must not replace legacy outputs"
    assert "endpoint_ids" in outputs and "endpoint_ids" in blocks, "new endpoint aggregate output may remain for new consumers"

    # Validate downstream fixture compatibility without editing the consumer.
    consumer_expected = read_json("stacks/app-consumer/expected_inputs.json")
    for name, value in consumer_expected.items():
        assert outputs[name]["value"] == value

    risks = s["protected_replacement_risks"]
    assert risks == [], risks

    state = read_json("fixtures/state_before_refactor.json")
    moved = s["moved_blocks"]
    for src, dst in state["legacy_resource_addresses"].items():
        assert moved.get(src) == dst, f"missing moved block {src} -> {dst}"

    migration_doc = (APP / "docs/migration_constraints.md").read_text(encoding="utf-8").lower()
    for term in ["legacy output", "moved", "non-destructive", "vpc", "subnet", "route table", "endpoint security group"]:
        assert term in migration_doc, f"migration notes should mention {term}"
    assert "current release status: pending" not in migration_doc, "release note still says pending"


class TestMilestone2:
    def test_inspector_runs_and_fixtures_remain_stable(self):
        """The offline inspector must run against unchanged incident fixtures."""
        s = summary()
        assert s["locals"].get("network_inventory"), "network inventory local was removed"
        assert_fixtures_not_rewritten()
        assert_core_module_present()


    def test_gateway_endpoint_coverage_is_private_and_complete(self):
        """S3 and DynamoDB gateway endpoints attach to every private route table and no public route tables."""
        assert_m2_contract(summary())

    def test_gateway_endpoints_are_not_deleted_or_retyped(self):
        """Coverage recovery must preserve gateway endpoint identity and endpoint type."""
        s = summary()
        endpoints = s["locals"]["gateway_vpc_endpoints"]
        assert endpoints["s3"]["id"] == "vpce-gw-s3"
        assert endpoints["dynamodb"]["id"] == "vpce-gw-dynamodb"
        assert endpoints["s3"]["vpc_endpoint_type"] == "Gateway"
        assert endpoints["dynamodb"]["vpc_endpoint_type"] == "Gateway"
