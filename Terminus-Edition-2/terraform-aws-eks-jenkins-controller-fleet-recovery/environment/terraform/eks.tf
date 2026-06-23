module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.11.1"
  cluster_name = var.cluster_name
  vpc_id = var.vpc_id
  subnet_ids = var.public_subnet_ids
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true
  eks_managed_node_groups = { default = { min_size = 1 max_size = 2 desired_size = 1 labels = { workload = "general" } } }
}
