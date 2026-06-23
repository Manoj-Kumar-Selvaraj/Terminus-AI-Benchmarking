# Incident timeline

A green EC2 module promotion launched from a mutable latest AMI alias instead of the release artifact. Security found public admin ingress and public IP associations on replacements. A failed canary terminated old capacity early; rollback kept service but exposed EBS, IAM, IMDS, and drift-reporting gaps.
