#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
from pathlib import Path
import json
root=Path('/app/terraform')
root.joinpath('eks.tf').write_text("""module "eks" {
  source = "terraform-aws-modules/eks/aws"
  version = "20.0.0"
  cluster_name = var.cluster_name
  vpc_id = var.vpc_id
  subnet_ids = var.private_subnet_ids
  cluster_endpoint_public_access = false
  cluster_endpoint_private_access = true
  eks_managed_node_groups = {
    system = { min_size = 2 max_size = 4 desired_size = 2 labels = { nodepool = "system" } taints = { critical = { key = "CriticalAddonsOnly" value = "true" effect = "NO_SCHEDULE" } } }
    apps = { min_size = 2 max_size = 6 desired_size = 3 labels = { nodepool = "apps" } }
    batch = { min_size = 0 max_size = 10 desired_size = 1 labels = { nodepool = "batch" } }
  }
}
""")
__PY__
