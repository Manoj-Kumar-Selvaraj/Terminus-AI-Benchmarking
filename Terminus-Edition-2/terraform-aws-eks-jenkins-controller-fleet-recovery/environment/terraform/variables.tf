variable "cluster_name" { type = string default = "prod-jenkins-eks" }
variable "vpc_id" { type = string default = "vpc-0aaabbb111222333" }
variable "private_subnet_ids" { type = list(string) default = ["subnet-private-a", "subnet-private-b", "subnet-private-c"] }
variable "public_subnet_ids" { type = list(string) default = ["subnet-public-a", "subnet-public-b", "subnet-public-c"] }
variable "aws_access_key" { type = string default = "DO-NOT-USE" }
variable "aws_secret_key" { type = string default = "DO-NOT-USE" }
