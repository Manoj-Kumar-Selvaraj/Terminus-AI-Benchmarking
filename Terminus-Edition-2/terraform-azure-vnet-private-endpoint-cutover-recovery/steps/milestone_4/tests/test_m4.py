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


def test_required_tags_are_merged_with_user_tags():
    """Required tags are merged with user tags."""
    tf = all_tf()
    assert 'local.required_tags' in tf
    for key in ['managed_by', 'data_classification', 'business_unit']:
        assert key in tf
    assert re.search(r'common_tags\s*=\s*merge\(\s*local\.required_tags\s*,\s*var\.tags\s*\)', tf, re.S)
    text = main_tf()
    vnet_block = block(text, 'resource "azurerm_virtual_network" "spoke"')
    nsg_block = block(text, 'resource "azurerm_network_security_group" "spoke"')
    assert 'tags' in vnet_block and 'local.common_tags' in vnet_block
    assert 'tags' in nsg_block and 'local.common_tags' in nsg_block


def test_vnet_diagnostics_are_sent_to_log_analytics():
    """Vnet diagnostics are sent to log analytics."""
    tf = all_tf()
    assert 'resource "azurerm_monitor_diagnostic_setting" "vnet"' in tf
    diag = re.search(r'resource\s+"azurerm_monitor_diagnostic_setting"\s+"vnet"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert diag
    body = diag.group('body')
    assert 'azurerm_virtual_network.spoke.id' in body
    assert 'var.log_analytics_workspace_id' in body
    assert 'VMProtectionAlerts' in body or 'enabled_log' in body


def test_nsg_diagnostics_are_created_for_each_nsg():
    """Nsg diagnostics are created for each nsg."""
    tf = all_tf()
    assert 'resource "azurerm_monitor_diagnostic_setting" "nsg"' in tf
    nsg = re.search(r'resource\s+"azurerm_monitor_diagnostic_setting"\s+"nsg"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert nsg
    body = nsg.group('body')
    assert re.search(r'for_each\s*=\s*azurerm_network_security_group\.spoke', body)
    assert re.search(r'category\s*=\s*"NetworkSecurityGroupEvent"', body)
    assert re.search(r'category\s*=\s*"NetworkSecurityGroupRuleCounter"', body)
    assert 'var.log_analytics_workspace_id' in body


def test_ddos_plan_attachment_is_conditional_and_not_created_unconditionally():
    """Ddos plan attachment is conditional and not created unconditionally."""
    tf = all_tf()
    vnet = re.search(r'resource\s+"azurerm_virtual_network"\s+"spoke"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert vnet
    body = vnet.group('body')
    assert 'dynamic "ddos_protection_plan"' in body
    assert 'var.enable_ddos_protection' in body
    assert 'var.ddos_protection_plan_id' in body


def test_management_lock_guards_the_vnet_scope():
    """Management lock guards the vnet scope."""
    tf = all_tf()
    assert 'resource "azurerm_management_lock" "vnet"' in tf
    lock = re.search(r'resource\s+"azurerm_management_lock"\s+"vnet"\s*{(?P<body>.*?)\n}', tf, re.S)
    assert lock
    body = lock.group('body')
    assert 'azurerm_virtual_network.spoke.id' in body
    assert 'CanNotDelete' in body


def test_all_downstream_outputs_are_present():
    """All downstream outputs are present."""
    out = read('outputs.tf')
    for name in ['vnet_id', 'vnet_name', 'subnet_ids', 'route_table_ids', 'nsg_ids', 'private_dns_zone_ids', 'private_endpoint_ids']:
        assert f'output "{name}"' in out
    for name in ['vnet_id', 'subnet_ids', 'route_table_ids', 'nsg_ids', 'private_dns_zone_ids', 'private_endpoint_ids']:
        match = re.search(rf'output\s+"{name}"\s*{{(.*?)}}', out, re.S)
        assert match, f'output {name} missing body'
        body = match.group(1)
        assert 'azurerm_' in body, f'{name} must reference a real module resource'

def test_diagnostics_use_supplied_workspace_variable_not_literal_or_empty_workspace():
    """Diagnostics use supplied workspace variable not literal or empty workspace."""
    text = main_tf()
    assert "log_analytics_workspace_id = var.log_analytics_workspace_id" in text
    assert 'log_analytics_workspace_id = ""' not in text
    assert "/subscriptions/" not in block(text, 'resource "azurerm_monitor_diagnostic_setting" "vnet"')


def test_ddos_block_is_dynamic_and_uses_existing_plan_id_only():
    """Ddos block is dynamic and uses existing plan id only."""
    text = main_tf()
    vnet_block = block(text, 'resource "azurerm_virtual_network" "spoke"')
    assert "dynamic \"ddos_protection_plan\"" in vnet_block
    assert "var.enable_ddos_protection" in vnet_block
    assert "var.ddos_protection_plan_id" in vnet_block
    assert 'resource "azurerm_network_ddos_protection_plan"' not in text
