# Milestone 4 — restore audit, tagging, DDoS, and delete guardrails

The production plan review also found missing diagnostic settings, inconsistent governance tags, no VNet delete guardrail and an unconditional DDoS change. Preserve all previous behavior while merging the required governance tags with caller-provided tags on managed resources.

Send VNet diagnostics and every NSG diagnostic stream to the supplied Log Analytics workspace, including NSG event and rule-counter categories. Attach an existing DDoS protection plan only when explicitly enabled, never create the shared DDoS plan in this module, add a `CanNotDelete` management lock at the VNet scope, and preserve the downstream outputs for the VNet, subnets, route tables, NSGs, Private DNS zones and private endpoints.
