#!/usr/bin/env python3
"""Offline semantic inspector for the staging network Terraform module.

The task intentionally does not need AWS credentials. This tool reads the
Terraform HCL files in modules/network, extracts jsondecode manifest locals,
parses output and moved-block declarations, and emits a normalized graph that
verifier tests can check semantically.
"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

APP = Path("/app")
LOCAL_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*jsondecode\(\s*<<([A-Z0-9_]+)\s*\n(.*?)\n\s*\2\s*\)", re.S)
OUTPUT_RE = re.compile(r'(?ms)^\s*output\s+"([^"]+)"\s*\{')
MOVED_RE = re.compile(r'(?ms)^\s*moved\s*\{\s*from\s*=\s*([^\n]+?)\s*\n\s*to\s*=\s*([^\n]+?)\s*\n\s*\}')
PROTECTED_TYPES = {
    "aws_vpc",
    "aws_subnet",
    "aws_route_table",
    "aws_nat_gateway",
    "aws_vpc_endpoint",
    "aws_security_group",
    "aws_route",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json_locals(module_dir: Path) -> dict[str, Any]:
    locals_map: dict[str, Any] = {}
    for tf in sorted(module_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for name, _marker, payload in LOCAL_RE.findall(text):
            try:
                locals_map[name] = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{tf}: local {name} contains invalid JSON: {exc}") from exc
    return locals_map


def parse_outputs(module_dir: Path) -> list[str]:
    names: list[str] = []
    for tf in sorted(module_dir.glob("*.tf")):
        names.extend(OUTPUT_RE.findall(tf.read_text(encoding="utf-8")))
    return sorted(set(names))


def parse_moved_blocks(module_dir: Path) -> dict[str, str]:
    moved: dict[str, str] = {}
    for tf in sorted(module_dir.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for src, dst in MOVED_RE.findall(text):
            clean_src = src.strip().rstrip(",")
            clean_dst = dst.strip().rstrip(",")
            moved[clean_src] = clean_dst
    return moved


def by_id(items: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {v.get("id"): {"key": k, **v} for k, v in items.items()}


def protected_replacement_risks(locals_map: dict[str, Any], state: dict[str, Any], moved: dict[str, str]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    inv = locals_map.get("network_inventory", {})

    if inv.get("environment") != state.get("environment"):
        risks.append({"resource_type": "environment", "reason": "environment name changed"})
    if inv.get("vpc", {}).get("id") != state.get("vpc", {}).get("id"):
        risks.append({"resource_type": "aws_vpc", "reason": "VPC ID changed"})
    if inv.get("vpc", {}).get("cidr_block") != state.get("vpc", {}).get("cidr_block"):
        risks.append({"resource_type": "aws_vpc", "reason": "VPC CIDR changed"})

    for family in ("subnets", "route_tables", "nat_gateways"):
        before = state.get(family, {})
        current = inv.get(family, {})
        if set(before.keys()) != set(current.keys()):
            risks.append({"resource_type": family, "reason": "stable keys changed", "before": sorted(before), "after": sorted(current)})
            continue
        for key, old in before.items():
            new = current[key]
            for attr in ("id", "cidr_block", "az", "tier"):
                if attr in old and old.get(attr) != new.get(attr):
                    risks.append({"resource_type": family, "key": key, "reason": f"{attr} changed", "before": old.get(attr), "after": new.get(attr)})

    gw = locals_map.get("gateway_vpc_endpoints", {})
    for key, old in state.get("gateway_endpoints", {}).items():
        if key not in gw:
            risks.append({"resource_type": "aws_vpc_endpoint", "key": key, "reason": "gateway endpoint deleted"})
        elif gw[key].get("id") != old.get("id"):
            risks.append({"resource_type": "aws_vpc_endpoint", "key": key, "reason": "gateway endpoint ID changed"})

    iface = locals_map.get("interface_vpc_endpoints", {})
    for key, old in state.get("interface_endpoints", {}).items():
        if key not in iface:
            risks.append({"resource_type": "aws_vpc_endpoint", "key": key, "reason": "interface endpoint deleted"})
        elif iface[key].get("id") != old.get("id"):
            risks.append({"resource_type": "aws_vpc_endpoint", "key": key, "reason": "interface endpoint ID changed"})

    endpoint_sg = inv.get("security_groups", {}).get("endpoint", {})
    old_sg = state.get("security_groups", {}).get("endpoint", {})
    if endpoint_sg.get("id") != old_sg.get("id"):
        risks.append({"resource_type": "aws_security_group", "reason": "endpoint SG ID changed"})

    # The saved state records refactor moves that need an explicit path. When a
    # source address equals target address, the pair is identity-preserving and
    # still allowed to be declared for auditability.
    required_moves = state.get("legacy_resource_addresses", {})
    missing = {src: dst for src, dst in required_moves.items() if moved.get(src) != dst}
    if missing:
        risks.append({"resource_type": "migration", "reason": "missing moved-block or migration map entries", "missing": missing})

    return risks


def build_summary(app: Path) -> dict[str, Any]:
    module_dir = app / "modules" / "network"
    fixtures_dir = app / "fixtures"
    locals_map = extract_json_locals(module_dir)
    output_blocks = parse_outputs(module_dir)
    moved = parse_moved_blocks(module_dir)
    state = read_json(fixtures_dir / "state_before_refactor.json")
    expected_routes = read_json(fixtures_dir / "expected_private_route_tables.json")
    expected_outputs = read_json(fixtures_dir / "expected_outputs.json")
    allowed_sources = read_json(fixtures_dir / "allowed_endpoint_sources.json")
    inv = locals_map.get("network_inventory", {})

    subnet_by_id = by_id(inv.get("subnets", {}))
    route_table_by_id = by_id(inv.get("route_tables", {}))
    associations = locals_map.get("route_table_associations", {})
    association_details = []
    for subnet_id, rt_id in associations.items():
        subnet = subnet_by_id.get(subnet_id)
        rt = route_table_by_id.get(rt_id)
        association_details.append({
            "subnet_id": subnet_id,
            "subnet_key": None if subnet is None else subnet.get("key"),
            "subnet_tier": None if subnet is None else subnet.get("tier"),
            "route_table_id": rt_id,
            "route_table_key": None if rt is None else rt.get("key"),
            "route_table_tier": None if rt is None else rt.get("tier"),
        })

    private_route_table_ids = sorted([v["id"] for v in inv.get("route_tables", {}).values() if v.get("tier") == "private"])
    public_route_table_ids = sorted([v["id"] for v in inv.get("route_tables", {}).values() if v.get("tier") == "public"])
    private_subnet_ids = sorted([v["id"] for v in inv.get("subnets", {}).values() if v.get("tier") == "private"])
    public_subnet_ids = sorted([v["id"] for v in inv.get("subnets", {}).values() if v.get("tier") == "public"])

    return {
        "locals": locals_map,
        "output_blocks": output_blocks,
        "moved_blocks": moved,
        "expected_routes": expected_routes,
        "expected_outputs": expected_outputs,
        "allowed_sources": allowed_sources,
        "subnet_by_id": subnet_by_id,
        "route_table_by_id": route_table_by_id,
        "association_details": sorted(association_details, key=lambda x: x["subnet_id"]),
        "private_route_table_ids": private_route_table_ids,
        "public_route_table_ids": public_route_table_ids,
        "private_subnet_ids": private_subnet_ids,
        "public_subnet_ids": public_subnet_ids,
        "gateway_endpoint_attachments": {k: sorted(v.get("route_table_ids", [])) for k, v in locals_map.get("gateway_vpc_endpoints", {}).items()},
        "interface_endpoints": locals_map.get("interface_vpc_endpoints", {}),
        "endpoint_security_group_rules": locals_map.get("endpoint_security_group_rules", {}),
        "module_output_contract": locals_map.get("module_output_contract", {}),
        "migration_notes": locals_map.get("migration_notes", {}),
        "protected_replacement_risks": protected_replacement_risks(locals_map, state, moved),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect offline Terraform network module contract")
    parser.add_argument("--app", default=str(APP), help="Application root, default /app")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    summary = build_summary(Path(args.app))
    print(json.dumps(summary, indent=2 if args.pretty else None, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
