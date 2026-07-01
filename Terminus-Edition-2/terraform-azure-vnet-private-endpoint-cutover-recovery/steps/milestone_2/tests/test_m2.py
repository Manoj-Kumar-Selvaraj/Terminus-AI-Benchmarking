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


def test_private_dns_zone_map_covers_required_services():
    """Private dns zone map covers required services."""
    tf = all_tf()
    for zone in [
        'privatelink.blob.core.windows.net',
        'privatelink.queue.core.windows.net',
        'privatelink.vaultcore.azure.net',
        'privatelink.database.windows.net',
    ]:
        assert zone in tf
    assert 'local.private_dns_zones' in tf


def test_private_dns_zones_are_linked_to_the_spoke_vnet():
    """Private dns zones are linked to the spoke vnet."""
    tf = all_tf()
    assert 'resource "azurerm_private_dns_zone" "private"' in tf
    assert re.search(r'resource\s+"azurerm_private_dns_zone"\s+"private"\s*{[^}]*for_each\s*=\s*local\.private_dns_zones', tf, re.S)
    assert 'resource "azurerm_private_dns_zone_virtual_network_link" "spoke"' in tf
    assert 'azurerm_virtual_network.spoke.id' in tf
    assert re.search(r'private_dns_zone_name\s*=\s*azurerm_private_dns_zone\.private\[each\.key\]\.name', tf)


def test_private_endpoints_use_dedicated_subnet_and_zone_group():
    """Private endpoints use dedicated subnet and zone group."""
    tf = all_tf()
    assert 'resource "azurerm_private_endpoint" "endpoint"' in tf
    pe = re.search(r'resource\s+"azurerm_private_endpoint"\s+"endpoint"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert pe, 'missing private endpoint resource'
    body = pe.group('body')
    assert re.search(r'for_each\s*=\s*var\.private_endpoints', body)
    assert 'azurerm_subnet.spoke[var.private_endpoint_subnet_key].id' in body
    assert 'private_service_connection' in body
    assert 'private_dns_zone_group' in body
    assert 'private_dns_zone_ids' in body


def test_private_endpoint_subnet_network_policy_is_disabled_only_for_pe_subnet():
    """Private endpoint subnet network policy is disabled only for pe subnet."""
    subnet_block = block(main_tf(), 'resource "azurerm_subnet" "spoke"')
    assert 'private_endpoint_network_policies' in subnet_block
    assert 'each.key == var.private_endpoint_subnet_key' in subnet_block
    assert 'Disabled' in subnet_block and 'Enabled' in subnet_block


def test_private_dns_and_endpoint_outputs_exist():
    """Private dns and endpoint outputs exist."""
    out = read('outputs.tf')
    assert 'output "private_dns_zone_ids"' in out
    assert 'output "private_endpoint_ids"' in out
    assert 'azurerm_private_dns_zone.private' in out
    assert 'azurerm_private_endpoint.endpoint' in out


def test_module_does_not_hardcode_azure_resource_ids_for_private_dns_or_pe():
    """Module does not hardcode azure resource ids for private dns or pe."""
    tf = all_tf()
    assert '/subscriptions/' not in tf
    assert 'Microsoft.Network/privateDnsZones' not in tf
    assert 'var.private_endpoints' in tf

def test_private_dns_links_disable_registration_and_use_managed_zone_names():
    """Private dns links disable registration and use managed zone names."""
    text = main_tf()
    link_block = block(text, 'resource "azurerm_private_dns_zone_virtual_network_link" "spoke"')
    assert "for_each" in link_block and "local.private_dns_zones" in link_block
    assert "registration_enabled  = false" in link_block or "registration_enabled=false" in compact(link_block)
    assert "private_dns_zone_name = azurerm_private_dns_zone.private[each.key].name" in link_block or "private_dns_zone_name=azurerm_private_dns_zone.private[each.key].name" in compact(link_block)


def test_private_endpoint_zone_group_uses_catalog_key_not_literal_zone_ids():
    """Private endpoint zone group uses catalog key not literal zone ids."""
    text = main_tf()
    pe_block = block(text, 'resource "azurerm_private_endpoint" "endpoint"')
    assert "private_dns_zone_group" in pe_block
    assert "azurerm_private_dns_zone.private[each.value.dns_zone_key].id" in pe_block
    assert "/subscriptions/" not in pe_block
    assert "private_dns_zone_ids = var." not in pe_block
