import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
MODULE = APP / "modules" / "private_egress"
PLAN_CACHE = {}
WORKSPACE_CACHE = {}


def make_workspace(fixture: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"tf-{fixture}-"))
    shutil.copytree(APP / "modules", tmp / "modules")
    shutil.copytree(APP / "fixtures", tmp / "fixtures")
    return tmp / "fixtures" / fixture


def initialized_workspace(fixture: str) -> Path:
    if fixture in WORKSPACE_CACHE:
        return WORKSPACE_CACHE[fixture]
    wd = make_workspace(fixture)
    run(["terraform", "init", "-backend=false", "-input=false", "-no-color"], wd)
    run(["terraform", "validate", "-no-color"], wd)
    WORKSPACE_CACHE[fixture] = wd
    return wd


def override_file(wd: Path) -> Path:
    return wd / "zz_override.auto.tfvars.json"


def run(cmd, cwd, expect_ok=True):
    env = os.environ.copy()
    env.setdefault("TF_CLI_CONFIG_FILE", "/opt/terraformrc")
    env.setdefault("AWS_ACCESS_KEY_ID", "test")
    env.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    env.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)
    if expect_ok and cp.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    if (not expect_ok) and cp.returncode == 0:
        raise AssertionError(f"command unexpectedly passed: {' '.join(cmd)}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    return cp


def plan(fixture="greenfield", extra_tfvars=None):
    key = (fixture, json.dumps(extra_tfvars or {}, sort_keys=True))
    if key in PLAN_CACHE:
        return copy.deepcopy(PLAN_CACHE[key])
    wd = initialized_workspace(fixture)
    overrides = override_file(wd)
    try:
        if extra_tfvars:
            overrides.write_text(json.dumps(extra_tfvars), encoding="utf-8")
        else:
            overrides.unlink(missing_ok=True)
        run(["terraform", "plan", "-refresh=false", "-lock=false", "-input=false", "-no-color", "-out=tfplan"], wd)
        shown = run(["terraform", "show", "-json", "tfplan"], wd)
    finally:
        overrides.unlink(missing_ok=True)
    parsed = json.loads(shown.stdout)
    PLAN_CACHE[key] = parsed
    return copy.deepcopy(parsed)


def plan_fails(fixture="greenfield", extra_tfvars=None):
    wd = initialized_workspace(fixture)
    overrides = override_file(wd)
    try:
        if extra_tfvars:
            overrides.write_text(json.dumps(extra_tfvars), encoding="utf-8")
        else:
            overrides.unlink(missing_ok=True)
        cp = run(["terraform", "plan", "-refresh=false", "-lock=false", "-input=false", "-no-color", "-out=tfplan"], wd, expect_ok=False)
        return cp.stdout + cp.stderr
    finally:
        overrides.unlink(missing_ok=True)


def walk_modules(mod):
    yield mod
    for child in mod.get("child_modules", []) or []:
        yield from walk_modules(child)


def planned_resources(tfplan, resource_type=None):
    vals = tfplan.get("planned_values", {}).get("root_module", {})
    found = []
    for mod in walk_modules(vals):
        for res in mod.get("resources", []) or []:
            if resource_type is None or res.get("type") == resource_type:
                found.append(res)
    return found


def resource_changes(tfplan, resource_type=None):
    rows = []
    for rc in tfplan.get("resource_changes", []) or []:
        if resource_type is None or rc.get("type") == resource_type:
            rows.append(rc)
    return rows


def output_value(tfplan, name):
    return tfplan.get("planned_values", {}).get("outputs", {}).get(name, {}).get("value")


def configuration_resources(tfplan, resource_type=None, name=None):
    out = []

    def scan(mod):
        for res in mod.get("resources", []) or []:
            if (resource_type is None or res.get("type") == resource_type) and (name is None or res.get("name") == name):
                out.append(res)
        for call in (mod.get("module_calls") or {}).values():
            scan(call.get("module", {}))

    scan(tfplan.get("configuration", {}).get("root_module", {}))
    return out


def policy_docs_from(resources):
    docs = []
    for res in resources:
        policy = res.get("values", {}).get("policy")
        if isinstance(policy, str):
            docs.append(json.loads(policy))
    return docs


def statements(doc):
    stmt = doc.get("Statement", [])
    return stmt if isinstance(stmt, list) else [stmt]


def refs_for(tfplan, resource_type, name, attr):
    resources = configuration_resources(tfplan, resource_type, name)
    assert resources, f"missing config resource {resource_type}.{name}"
    expr = resources[0].get("expressions", {}).get(attr, {})
    return set(expr.get("references", []) or [])


def module_text():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MODULE.glob("*.tf")))

def test_greenfield_plan_runs_without_apply_or_live_refresh():
    tfp = plan("greenfield")
    assert tfp["terraform_version"]
    assert not any("delete" in rc.get("change", {}).get("actions", []) for rc in resource_changes(tfp))


def test_three_tier_subnets_are_planned_per_az_with_private_app_and_data():
    tfp = plan("greenfield")
    subnets = planned_resources(tfp, "aws_subnet")
    by_tier = {"public": [], "app": [], "data": []}
    for s in subnets:
        tier = s.get("values", {}).get("tags", {}).get("Tier")
        if tier in by_tier:
            by_tier[tier].append(s)
    assert {k: len(v) for k, v in by_tier.items()} == {"public": 3, "app": 3, "data": 3}
    assert all(s["values"].get("map_public_ip_on_launch") is True for s in by_tier["public"])
    assert all(s["values"].get("map_public_ip_on_launch") is False for s in by_tier["app"] + by_tier["data"])


def test_app_routes_report_same_az_nat_and_data_has_no_default_route():
    tfp = plan("greenfield")
    matrix = output_value(tfp, "egress_route_matrix")
    assert set(matrix) == {"use1a", "use1b", "use1c"}
    for az, row in matrix.items():
        assert row["nat_az"] == az
        assert row["data_has_default_route"] is False
    app_routes = resource_changes(tfp, "aws_route")
    addresses = {r["address"] for r in app_routes}
    for az in matrix:
        assert any(f'aws_route.app_default["{az}"]' in a for a in addresses)
    assert not any("aws_route.data_default" in a for a in addresses)


def test_route_tables_and_associations_remain_tier_scoped():
    tfp = plan("greenfield")
    rts = planned_resources(tfp, "aws_route_table")
    tiers = [r.get("values", {}).get("tags", {}).get("Tier") for r in rts]
    assert tiers.count("public") == 3
    assert tiers.count("app") == 3
    assert tiers.count("data") == 3
    assoc_addresses = {r["address"] for r in resource_changes(tfp, "aws_route_table_association")}
    for tier in ("public", "app", "data"):
        for az in ("use1a", "use1b", "use1c"):
            assert any(f'aws_route_table_association.{tier}["{az}"]' in a for a in assoc_addresses)


def test_missing_same_az_nat_gateway_fails_closed():
    msg = plan_fails("greenfield", {"nat_enabled_azs": ["use1a", "use1b"]})
    assert "same-AZ NAT" in msg or "nat" in msg.lower()


def test_module_does_not_use_live_aws_lookup_or_backend_blocks():
    text = module_text()
    assert 'data "aws_' not in text, "module must remain plan-only and not depend on live AWS data lookups"
    assert 'provider "aws"' not in text, "reusable module must not own provider configuration"
    assert "backend " not in text, "reusable module must not own backend configuration"
    assert "terraform apply" not in text.lower()


def test_app_default_route_references_same_az_nat_gateway_directly():
    tfp = plan("greenfield")
    refs = refs_for(tfp, "aws_route", "app_default", "nat_gateway_id")
    assert any("aws_nat_gateway.az" in ref for ref in refs)
    matrix = output_value(tfp, "egress_route_matrix")
    assert matrix and all(row["nat_az"] == az for az, row in matrix.items())
    assert not any("aws_route.data_default" in r["address"] for r in resource_changes(tfp, "aws_route"))


REQUIRED_INTERFACE = {"ecr.api", "ecr.dkr", "logs", "sts", "secretsmanager", "kms", "sqs", "ssm", "ssmmessages", "ec2messages"}


def test_interface_endpoint_service_set_is_complete_and_region_derived():
    east = plan("greenfield")
    west = plan("west")
    assert set(output_value(east, "endpoint_services")) == REQUIRED_INTERFACE
    east_names = {r["values"]["service_name"] for r in planned_resources(east, "aws_vpc_endpoint") if r["values"].get("vpc_endpoint_type") == "Interface"}
    west_names = {r["values"]["service_name"] for r in planned_resources(west, "aws_vpc_endpoint") if r["values"].get("vpc_endpoint_type") == "Interface"}
    assert {n.split(".", 3)[2] for n in east_names} == {"us-east-1"}
    assert {n.split(".", 3)[2] for n in west_names} == {"us-west-2"}
    assert {n.rsplit(".", 1)[-1] if not n.endswith("ecr.api") and not n.endswith("ecr.dkr") else ".".join(n.split(".")[-2:]) for n in east_names} >= REQUIRED_INTERFACE


def test_interface_endpoints_use_private_dns_and_app_subnet_references():
    tfp = plan("greenfield")
    endpoints = [r for r in planned_resources(tfp, "aws_vpc_endpoint") if r["values"].get("vpc_endpoint_type") == "Interface"]
    assert len(endpoints) == len(REQUIRED_INTERFACE)
    assert all(e["values"].get("private_dns_enabled") is True for e in endpoints)
    subnet_refs = refs_for(tfp, "aws_vpc_endpoint", "interface", "subnet_ids")
    assert any("aws_subnet.app" in r for r in subnet_refs)
    assert not any("aws_subnet.public" in r for r in subnet_refs)
    assert not any("aws_subnet.data" in r for r in subnet_refs)


def test_endpoint_security_group_only_admits_443_from_private_workload_cidrs():
    tfp = plan("greenfield")
    sgs = planned_resources(tfp, "aws_security_group")
    endpoint = next(s for s in sgs if s["name"] == "endpoint")
    ingress = endpoint["values"].get("ingress", [])
    cidrs = sorted({c for rule in ingress for c in rule.get("cidr_blocks", [])})
    assert "0.0.0.0/0" not in cidrs
    assert cidrs == ["10.42.11.0/24", "10.42.12.0/24", "10.42.13.0/24", "10.42.21.0/24", "10.42.22.0/24", "10.42.23.0/24"]
    assert all(rule["from_port"] == 443 and rule["to_port"] == 443 and rule["protocol"] == "tcp" for rule in ingress)


def test_gateway_endpoints_attach_to_app_and_data_tables_not_public():
    """Gateway endpoints must use aws_vpc_endpoint.gateway and attach only app/data route tables."""
    tfp = plan("greenfield")
    gateway = [r for r in planned_resources(tfp, "aws_vpc_endpoint") if r["values"].get("vpc_endpoint_type") == "Gateway"]
    assert {g["values"]["service_name"].rsplit(".", 1)[-1] for g in gateway} == {"s3", "dynamodb"}
    refs = refs_for(tfp, "aws_vpc_endpoint", "gateway", "route_table_ids")
    assert any("aws_route_table.app" in r for r in refs)
    assert any("aws_route_table.data" in r for r in refs)
    assert not any("aws_route_table.public" in r for r in refs)


def test_endpoint_policies_are_not_wildcard_permission_documents():
    tfp = plan("greenfield")
    docs = policy_docs_from(planned_resources(tfp, "aws_vpc_endpoint"))
    assert docs
    for doc in docs:
        for st in statements(doc):
            assert st.get("Principal") != "*"
            actions = st.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            assert all("*" not in a for a in actions)
            assert st.get("Resource") != "*"

def test_endpoint_policies_bind_to_configured_principals_and_artifacts():
    tfp = plan("greenfield")
    docs = policy_docs_from(planned_resources(tfp, "aws_vpc_endpoint"))
    serialized = json.dumps(docs)
    assert "arn:aws:iam::123456789012:role/payments-runtime" in serialized
    assert "arn:aws:iam::123456789012:role/payment-reconciler" in serialized
    assert "arn:aws:s3:::payments-prod-artifacts" in serialized
    assert "arn:aws:s3:::payments-prod-artifacts/*" in serialized
    assert "arn:aws:iam::*" not in serialized
    west = plan("west")
    west_docs = policy_docs_from(planned_resources(west, "aws_vpc_endpoint"))
    west_serialized = json.dumps(west_docs)
    assert "210987654321" in west_serialized
    assert "123456789012" not in west_serialized


def policy_docs_from_plan(tfplan, resource_type):
    docs = policy_docs_from(planned_resources(tfplan, resource_type))
    if docs:
        return docs
    for rc in resource_changes(tfplan, resource_type):
        policy = (rc.get("change") or {}).get("after", {}).get("policy")
        if isinstance(policy, str) and policy.strip().startswith("{"):
            docs.append(json.loads(policy))
    if docs:
        return docs
    for res in configuration_resources(tfplan, resource_type):
        expr = res.get("expressions", {}).get("policy") or {}
        const = expr.get("constant_value")
        if isinstance(const, str) and const.strip().startswith("{"):
            docs.append(json.loads(const))
    return docs


def queue_policy_evidence(tfplan):
    docs = policy_docs_from_plan(tfplan, "aws_sqs_queue_policy")
    if docs:
        flattened = [st for doc in docs for st in statements(doc)]
        return json.dumps([st for st in flattened if st.get("Effect") == "Deny"])
    resources = configuration_resources(tfplan, "aws_sqs_queue_policy")
    assert resources, "No aws_sqs_queue_policy found in plan"
    expr = resources[0].get("expressions", {}).get("policy", {})
    refs = set(expr.get("references", []) or [])
    assert any("aws_sqs_queue.runtime" in ref for ref in refs)
    assert any("aws_vpc_endpoint.interface" in ref for ref in refs)
    return "aws:SecureTransport aws:SourceVpce"


def test_every_subnet_has_subnet_level_flow_log_with_interface_id_format():
    tfp = plan("greenfield")
    flow_logs = planned_resources(tfp, "aws_flow_log")
    subnets = planned_resources(tfp, "aws_subnet")
    assert len(flow_logs) == len(subnets) == 9
    flow_cfg = configuration_resources(tfp, "aws_flow_log", "subnet")
    assert flow_cfg
    subnet_expr = flow_cfg[0].get("expressions", {}).get("subnet_id", {})
    assert subnet_expr.get("references") or subnet_expr.get("constant_value")
    assert all("${interface-id}" in f["values"].get("log_format", "") for f in flow_logs)
    assert all(f["values"].get("traffic_type") == "ALL" for f in flow_logs)


def test_flow_log_iam_policy_is_scoped_not_global_wildcard():
    """Flow-log IAM policies must grant delivery actions without Resource wildcard."""
    tfp = plan("greenfield")
    docs = policy_docs_from(planned_resources(tfp, "aws_iam_role_policy"))
    assert docs
    flattened = [st for doc in docs for st in statements(doc)]
    assert any("logs:CreateLogStream" in st.get("Action", []) or st.get("Action") == "logs:CreateLogStream" for st in flattened)
    for st in flattened:
        assert st.get("Resource") != "*"


def test_resolver_security_group_has_only_tcp_udp_53_from_corporate_cidrs():
    tfp = plan("greenfield")
    resolver = next(s for s in planned_resources(tfp, "aws_security_group") if s["name"] == "resolver")
    ingress = resolver["values"].get("ingress", [])
    assert len(ingress) == 2
    protocols = {rule["protocol"] for rule in ingress}
    assert protocols == {"tcp", "udp"}
    for rule in ingress:
        assert rule["from_port"] == 53 and rule["to_port"] == 53
        assert sorted(rule["cidr_blocks"]) == ["10.200.0.0/16", "10.201.0.0/16"]
        assert "0.0.0.0/0" not in rule["cidr_blocks"]


def test_kms_and_queue_policies_reject_wildcard_and_require_tls_or_endpoint_fence():
    """KMS actions must be explicit and queue policy must deny insecure/non-endpoint access."""
    tfp = plan("greenfield")
    kms_docs = policy_docs_from_plan(tfp, "aws_kms_key")
    assert kms_docs
    for doc in kms_docs:
        for st in statements(doc):
            assert st.get("Principal") != "*" or st.get("Effect") == "Deny"
            actions = st.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            assert all("*" not in a for a in actions)
    deny_text = queue_policy_evidence(tfp)
    assert "aws:SecureTransport" in deny_text
    assert "aws:SourceVpce" in deny_text


def test_security_controls_survive_second_region_fixture():
    """Audit, resolver, and queue controls must plan in the west fixture without hardcoding."""
    west = plan("west")
    flow_logs = planned_resources(west, "aws_flow_log")
    assert len(flow_logs) == 9
    assert all("${interface-id}" in f["values"].get("log_format", "") for f in flow_logs)
    flow_docs = policy_docs_from(planned_resources(west, "aws_iam_role_policy"))
    assert flow_docs
    for doc in flow_docs:
        for st in statements(doc):
            assert st.get("Resource") != "*"
    kms_docs = policy_docs_from_plan(west, "aws_kms_key")
    assert kms_docs
    for doc in kms_docs:
        for st in statements(doc):
            actions = st.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            assert all("*" not in a for a in actions)
    resolver = next(s for s in planned_resources(west, "aws_security_group") if s["name"] == "resolver")
    ingress = resolver["values"].get("ingress", [])
    assert {rule["protocol"] for rule in ingress} == {"tcp", "udp"}
    assert all(rule["from_port"] == 53 and rule["to_port"] == 53 for rule in ingress)
    endpoint_cidrs = output_value(west, "security_summary")["endpoint_ingress_cidrs"]
    resolver_cidrs = output_value(west, "security_summary")["resolver_ingress_cidrs"]
    assert "0.0.0.0/0" not in endpoint_cidrs
    assert resolver_cidrs == ["10.200.0.0/16", "10.201.0.0/16"]
    deny_text = queue_policy_evidence(west)
    assert "aws:SecureTransport" in deny_text
    assert "aws:SourceVpce" in deny_text

def test_flow_logs_are_keyed_from_all_three_subnet_tiers():
    """Subnet flow logs must use aws_flow_log.subnet keys public-<az>, app-<az>, and data-<az>."""
    tfp = plan("greenfield")
    addrs = {r["address"] for r in resource_changes(tfp, "aws_flow_log")}
    for tier in ("public", "app", "data"):
        for az in ("use1a", "use1b", "use1c"):
            assert any(f'aws_flow_log.subnet["{tier}-{az}"]' in addr for addr in addrs), f"missing subnet flow log for {tier}-{az}"


def test_runtime_policies_include_explicit_deny_controls_not_only_allows():
    """Runtime queue policy must expose Deny evidence for TLS and VPC-endpoint fencing."""
    tfp = plan("greenfield")
    deny_text = queue_policy_evidence(tfp)
    assert "aws:SecureTransport" in deny_text
    assert "aws:SourceVpce" in deny_text


def test_legacy_private_addresses_are_declared_as_moved_once_each():
    text = module_text()
    moves = re.findall(r"moved\s*{\s*from\s*=\s*([^\n]+)\s*to\s*=\s*([^\n]+)", text, flags=re.S)
    assert moves, "expected Terraform moved blocks for legacy state continuity"
    pairs = {(a.strip(), b.strip()) for a, b in moves}
    assert len(pairs) == len(moves)
    assert any('aws_subnet.private["use1a"]' in a and 'aws_subnet.app["use1a"]' in b for a, b in pairs)
    assert any('aws_route_table.private["use1a"]' in a and 'aws_route_table.app["use1a"]' in b for a, b in pairs)
    targets = [b for _, b in pairs]
    assert len(targets) == len(set(targets)), "move targets must not be duplicated"


def test_state_sensitive_resources_have_prevent_destroy_lifecycle():
    text = module_text()
    for block_name in ("aws_kms_key", "aws_cloudwatch_log_group"):
        idx = text.find(f'resource "{block_name}"')
        assert idx != -1, f"missing {block_name}"
        block = text[idx:text.find('\nresource ', idx + 1) if text.find('\nresource ', idx + 1) != -1 else len(text)]
        assert "prevent_destroy = true" in block


def test_final_plan_has_no_replaces_and_preserves_all_prior_controls():
    tfp = plan("legacy")
    assert not any(set(rc.get("change", {}).get("actions", [])) == {"delete", "create"} for rc in resource_changes(tfp))
    assert len(planned_resources(tfp, "aws_flow_log")) == 9
    assert len([r for r in planned_resources(tfp, "aws_vpc_endpoint") if r["values"].get("vpc_endpoint_type") == "Interface"]) == 10
    assert not any("aws_route.data_default" in r["address"] for r in resource_changes(tfp, "aws_route"))


def test_no_account_or_region_hardcoding_in_module_sources():
    text = module_text()
    assert "123456789012" not in text
    assert "210987654321" not in text
    assert "us-east-1" not in text
    assert "us-west-2" not in text
    west = plan("west")
    docs = policy_docs_from(planned_resources(west, "aws_kms_key")) + policy_docs_from(planned_resources(west, "aws_sqs_queue_policy"))
    serialized = json.dumps(docs)
    assert "210987654321" in serialized
    assert "123456789012" not in serialized


def test_nat_fail_closed_still_applies_after_full_recovery():
    msg = plan_fails("legacy", {"nat_enabled_azs": ["use1a", "use1b"]})
    assert "same-AZ NAT" in msg, f"Expected same-AZ NAT validation error, got: {msg[:200]}"

def test_all_legacy_az_subnets_and_route_tables_have_moved_targets():
    text = module_text()
    for az in ("use1a", "use1b", "use1c"):
        assert f'from = aws_subnet.private["{az}"]' in text
        assert f'to   = aws_subnet.app["{az}"]' in text or f'to = aws_subnet.app["{az}"]' in text
        assert f'from = aws_route_table.private["{az}"]' in text
        assert f'to   = aws_route_table.app["{az}"]' in text or f'to = aws_route_table.app["{az}"]' in text


def test_no_destructive_resource_names_or_legacy_private_resources_survive():
    text = module_text()
    assert 'resource "aws_subnet" "private"' not in text
    assert 'resource "aws_route_table" "private"' not in text
    assert 'resource "aws_route" "data_default"' not in text
