import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
MOD = APP / "terraform" / "modules" / "secure-vnet"


def read(name: str) -> str:
    return (MOD / name).read_text(encoding="utf-8")


def all_tf() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MOD.glob("*.tf")))


def compact(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def test_legacy_state_addresses_have_moved_blocks():
    """Legacy state addresses have moved blocks."""
    tf = all_tf()
    expected = [
        ('azurerm_subnet.app', 'azurerm_subnet.spoke["app"]'),
        ('azurerm_subnet.data', 'azurerm_subnet.spoke["data"]'),
        ('azurerm_route_table.default', 'azurerm_route_table.spoke["app"]'),
        ('azurerm_subnet_route_table_association.app', 'azurerm_subnet_route_table_association.spoke["app"]'),
    ]
    for old, new in expected:
        assert old in tf, f'missing moved-from {old}'
        assert new in tf, f'missing moved-to {new}'
    assert tf.count('moved {') >= 4


def test_network_resources_have_prevent_destroy_lifecycle_guards():
    """Network resources have prevent destroy lifecycle guards."""
    tf = all_tf()
    for resource in ['azurerm_virtual_network" "spoke', 'azurerm_subnet" "spoke', 'azurerm_route_table" "spoke', 'azurerm_private_dns_zone" "private']:
        pattern = r'resource\s+"' + re.escape(resource.split('" "')[0]) + r'"\s+"' + re.escape(resource.split('" "')[1]) + r'"\s*{(?P<body>.*?)\n}'
        match = re.search(pattern, tf, re.S)
        assert match, f'missing resource {resource}'
        assert 'prevent_destroy = true' in match.group('body'), f'{resource} must guard against destroy'


def test_private_endpoint_precondition_requires_valid_subnet_key():
    """Private endpoint precondition requires valid subnet key."""
    tf = all_tf()
    pe = re.search(r'resource\s+"azurerm_private_endpoint"\s+"endpoint"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert pe
    body = pe.group('body')
    precon = re.search(r'precondition\s*{(.*?)}', body, re.S)
    assert precon, 'missing precondition block'
    cond = precon.group(1)
    assert 'var.private_endpoint_subnet_key' in cond
    assert 'contains(' in cond
    assert 'keys(var.subnets)' in cond or 'keys(azurerm_subnet.spoke)' in cond


def test_admin_cidr_validation_rejects_anywhere_rules():
    """Admin cidr validation rejects anywhere rules."""
    vars_tf = read('variables.tf')
    assert 'variable "allowed_admin_cidrs"' in vars_tf
    start = vars_tf.find('variable "allowed_admin_cidrs"')
    end = vars_tf.find('\nvariable ', start + 1)
    admin_var = vars_tf[start:end if end != -1 else len(vars_tf)]
    val_block = re.search(r'validation\s*{(.*?)}', admin_var, re.S)
    assert val_block, 'missing validation block'
    cond = val_block.group(1)
    assert 'alltrue' in cond
    assert '0.0.0.0/0' in cond and '::/0' in cond
    assert re.search(r'!=|!contains', cond)


def test_no_live_lookup_or_nondeterministic_resources_are_used():
    """No live lookup or nondeterministic resources are used."""
    tf = all_tf()
    assert 'data "azurerm_' not in tf
    assert 'resource "random_' not in tf
    for fn in ['timestamp(', 'uuid(', 'filemd5(']:
        assert fn not in tf


def test_solution_keeps_plan_only_module_contract_not_apply_artifacts():
    """Solution keeps plan only module contract not apply artifacts."""
    tf = all_tf()
    assert 'azurerm_resource_group' not in tf, 'module must not create the shared production resource group'
    assert 'provider "azurerm"' not in tf, 'module should not own provider configuration'
    assert 'backend ' not in tf, 'module should not configure remote backend'


def test_moved_targets_are_unique_and_cover_legacy_route_association():
    """Moved targets are unique and cover legacy route association."""
    text = all_tf()
    moved_targets = re.findall(r"moved\s*{\s*from\s*=\s*[^\n]+\s*to\s*=\s*([^\n]+)", text, flags=re.S)
    assert moved_targets
    normalized = [target.strip() for target in moved_targets]
    assert len(normalized) == len(set(normalized))
    assert 'azurerm_subnet_route_table_association.spoke["app"]' in normalized


def test_no_generated_state_or_cloud_snapshot_artifacts_are_committed():
    """No generated state or cloud snapshot artifacts are committed."""
    forbidden_suffixes = {".tfstate", ".tfstate.backup", ".tfplan"}
    for path in APP.rglob("*"):
        if path.is_file():
            assert path.suffix not in forbidden_suffixes, f"forbidden generated Terraform artifact: {path}"
            assert path.name not in {"terraform.tfstate", "tfplan", "cloud_state.json", "plan.json"}
