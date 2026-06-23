# Service aliases

Allowed canonical source services are `ER`, `LAB`, and `IMG`.

Legacy action aliases normalize case-insensitively after trimming: `E1` → `ER`, `LB` → `LAB`, `XR` → `IMG`.

Alias normalization does not relax the source-side canonical service gate. Source rows whose service is not `ER`, `LAB`, or `IMG` remain ineligible even when the action alias normalizes to the same literal text.
