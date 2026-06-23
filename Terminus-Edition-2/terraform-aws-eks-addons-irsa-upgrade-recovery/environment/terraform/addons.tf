resource "aws_iam_role_policy_attachment" "node_addon_admin" { role = module.eks.eks_managed_node_groups.default.iam_role_name policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess" }
resource "helm_release" "aws_load_balancer_controller" { name = "aws-load-balancer-controller" set { name = "serviceAccount.annotations.eks\.amazonaws\.com/role-arn" value = "" } }
