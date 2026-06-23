# The refactor changed several list-indexed resources to named resources, but
# this migration file has not yet recorded an explicit compatibility path.
locals {
  migration_notes = jsondecode(<<JSON
{
  "identity_policy": "pending-review",
  "operator_note": "saved plan still shows replacement risk for stable network resources"
}
JSON
  )
}
