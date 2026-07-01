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


def test_subnets_are_data_driven_not_legacy_singletons():
    """Subnets are data driven not legacy singletons."""
    tf = all_tf()
    assert 'resource "azurerm_subnet" "spoke"' in tf
    assert re.search(r'resource\s+"azurerm_subnet"\s+"spoke"\s*{[^}]*for_each\s*=\s*var\.subnets', tf, re.S)
    assert 'resource "azurerm_subnet" "app"' not in tf
    assert 'resource "azurerm_subnet" "data"' not in tf
    assert '10.42.1.0/24' not in tf and '10.42.2.0/24' not in tf


def test_default_routes_are_to_firewall_virtual_appliance_only():
    """Default routes are to firewall virtual appliance only."""
    tf = all_tf()
    assert 'resource "azurerm_route" "default_egress"' in tf
    route = re.search(r'resource\s+"azurerm_route"\s+"default_egress"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert route, 'missing default_egress route resource'
    body = route.group('body')
    assert 'address_prefix' in body and '0.0.0.0/0' in body
    assert re.search(r'next_hop_type\s*=\s*"VirtualAppliance"', body)
    assert re.search(r'next_hop_in_ip_address\s*=\s*var\.firewall_private_ip', body)
    assert 'Internet' not in body


def test_route_tables_are_per_routeable_subnet_and_exclude_platform_subnets():
    """Route tables are per routeable subnet and exclude platform subnets."""
    tf = all_tf()
    assert 'local.routeable_subnets' in tf
    assert 'var.private_endpoint_subnet_key' in tf
    for reserved in ['AzureFirewallSubnet', 'GatewaySubnet', 'AzureBastionSubnet']:
        assert reserved in tf
    assert re.search(r'resource\s+"azurerm_route_table"\s+"spoke"\s*{[^}]*for_each\s*=\s*local\.routeable_subnets', tf, re.S)
    assert re.search(r'resource\s+"azurerm_route"\s+"default_egress"\s*{[^}]*for_each\s*=\s*local\.routeable_subnets', tf, re.S)


def test_route_table_association_uses_same_logical_subnet_key():
    """Route table association uses same logical subnet key."""
    tf = all_tf()
    assoc = re.search(r'resource\s+"azurerm_subnet_route_table_association"\s+"spoke"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert assoc, 'missing route-table association resource'
    body = assoc.group('body')
    assert re.search(r'for_each\s*=\s*local\.routeable_subnets', body)
    assert 'azurerm_subnet.spoke[each.key].id' in body
    assert 'azurerm_route_table.spoke[each.key].id' in body


def test_required_m1_outputs_preserve_downstream_shape():
    """Required m1 outputs preserve downstream shape."""
    out = read('outputs.tf')
    assert 'output "vnet_id"' in out
    assert 'output "subnet_ids"' in out
    assert re.search(r'for\s+k\s*,\s*subnet\s+in\s+azurerm_subnet\.spoke\s*:\s*k\s*=>\s*subnet\.id', out, re.S)


def test_firewall_ip_and_subnets_have_validation_contracts():
    """Firewall ip and subnets have validation contracts."""
    vars_tf = read('variables.tf')
    assert 'variable "firewall_private_ip"' in vars_tf
    start = vars_tf.find('variable "firewall_private_ip"')
    end = vars_tf.find('\nvariable ', start + 1)
    fw_var = vars_tf[start:end if end != -1 else len(vars_tf)]
    val_block = re.search(r'validation\s*{(.*?)}', fw_var, re.S)
    assert val_block, 'missing firewall_private_ip validation block'
    cond = val_block.group(1)
    assert 'var.firewall_private_ip' in cond
    assert 'can(cidrhost' in cond or 'length(' in cond or '!= ""' in cond
    assert 'variable "subnets"' in vars_tf
    assert 'route_table_enabled' in vars_tf and 'nsg_enabled' in vars_tf

def test_module_does_not_own_provider_backend_or_shared_resource_group():
    """Module does not own provider backend or shared resource group."""
    text = all_tf()
    assert 'provider "azurerm"' not in text
    assert 'backend ' not in text
    assert 'resource "azurerm_resource_group"' not in text
    assert "terraform apply" not in text.lower()


def test_platform_subnet_filter_includes_firewall_gateway_bastion_and_private_endpoint_key():
    """Platform subnet filter includes firewall gateway bastion and private endpoint key."""
    text = main_tf()
    assert "platform_subnet_keys" in text
    for key in ("AzureFirewallSubnet", "GatewaySubnet", "AzureBastionSubnet"):
        assert key in text
    assert "var.private_endpoint_subnet_key" in text
    assert "!contains(local.platform_subnet_keys, key)" in compact(text) or "!contains(local.platform_subnet_keys,key)" in compact(text)
