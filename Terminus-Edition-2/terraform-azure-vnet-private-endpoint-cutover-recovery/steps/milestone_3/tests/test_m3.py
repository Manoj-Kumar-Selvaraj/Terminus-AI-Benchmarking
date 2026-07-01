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


def main_tf() -> str:
    return read("main.tf")


def block(text: str, marker: str) -> str:
    start = text.find(marker)
    assert start != -1, f"missing block {marker}"
    candidates = [idx for idx in [text.find("\nresource ", start + 1), text.find("\noutput ", start + 1), text.find("\nmoved ", start + 1)] if idx != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def test_nsgs_and_associations_are_created_per_enabled_subnet():
    """Nsgs and associations are created per enabled subnet."""
    tf = all_tf()
    assert 'local.nsg_subnets' in tf
    assert re.search(r'nsg_subnets\s*=\s*\{[^}]*nsg_enabled', tf, re.S)
    assert 'resource "azurerm_network_security_group" "spoke"' in tf
    assert re.search(r'resource\s+"azurerm_network_security_group"\s+"spoke"\s*{[^}]*for_each\s*=\s*local\.nsg_subnets', tf, re.S)
    assert 'resource "azurerm_subnet_network_security_group_association" "spoke"' in tf
    assert 'azurerm_subnet.spoke[each.key].id' in tf
    assert 'azurerm_network_security_group.spoke[each.key].id' in tf


def test_internet_inbound_is_explicitly_denied_not_allowed():
    """Internet inbound is explicitly denied not allowed."""
    tf = all_tf()
    assert 'resource "azurerm_network_security_rule" "deny_internet_inbound"' in tf
    deny = re.search(r'resource\s+"azurerm_network_security_rule"\s+"deny_internet_inbound"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert deny
    body = deny.group('body')
    assert 'Internet' in body
    assert re.search(r'access\s*=\s*"Deny"', body)
    assert re.search(r'direction\s*=\s*"Inbound"', body)
    assert not re.search(r'source_address_prefix\s*=\s*"(\*|0\.0\.0\.0/0)"[^}]*access\s*=\s*"Allow"', tf, re.S)


def test_app_ingress_is_from_application_gateway_on_declared_ports():
    """App ingress is from application gateway on declared ports."""
    tf = all_tf()
    assert 'resource "azurerm_network_security_rule" "allow_app_gateway_to_app"' in tf
    rule = re.search(r'resource\s+"azurerm_network_security_rule"\s+"allow_app_gateway_to_app"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert rule
    body = rule.group('body')
    assert 'local.app_subnets' in body
    assert 'var.application_gateway_subnet_cidr' in body
    assert 'var.app_ports' in body
    assert 'Allow' in body and 'Inbound' in body


def test_data_tier_ingress_is_only_from_app_subnet_prefixes():
    """Data tier ingress is only from app subnet prefixes."""
    tf = all_tf()
    assert 'local.app_subnet_prefixes' in tf
    assert 'resource "azurerm_network_security_rule" "allow_app_to_data"' in tf
    rule = re.search(r'resource\s+"azurerm_network_security_rule"\s+"allow_app_to_data"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert rule
    body = rule.group('body')
    assert 'local.data_subnets' in body
    assert 'source_address_prefixes' in body
    assert 'local.app_subnet_prefixes' in body
    assert 'Internet' not in body


def test_route_tables_disable_bgp_propagation_for_forced_egress():
    """Route tables disable bgp propagation for forced egress."""
    tf = all_tf()
    rt = re.search(r'resource\s+"azurerm_route_table"\s+"spoke"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert rt
    assert re.search(r'disable_bgp_route_propagation\s*=\s*true', rt.group('body'))


def test_nsg_rules_are_not_single_static_app_or_data_resources():
    """Nsg rules are not single static app or data resources."""
    tf = all_tf()
    assert 'for_each = local.app_subnets' in tf
    assert 'for_each = local.data_subnets' in tf

def test_security_rule_priorities_keep_specific_allows_before_internet_deny():
    """Security rule priorities keep specific allows before internet deny."""
    text = main_tf()
    app_block = block(text, 'resource "azurerm_network_security_rule" "allow_app_gateway_to_app"')
    data_block = block(text, 'resource "azurerm_network_security_rule" "allow_app_to_data"')
    deny_block = block(text, 'resource "azurerm_network_security_rule" "deny_internet_inbound"')
    assert "priority                    = 110" in app_block or "priority=110" in compact(app_block)
    assert "priority                     = 120" in data_block or "priority=120" in compact(data_block)
    assert "priority                    = 4096" in deny_block or "priority=4096" in compact(deny_block)


def test_data_tier_ports_are_limited_to_approved_service_ports():
    """Data tier ports are limited to approved service ports."""
    text = main_tf()
    data_block = block(text, 'resource "azurerm_network_security_rule" "allow_app_to_data"')
    for port in ('"1433"', '"5432"', '"6379"'):
        assert port in data_block
    assert "destination_port_range      = \"*\"" not in data_block
    assert "destination_port_ranges      = [\"*\"]" not in data_block
