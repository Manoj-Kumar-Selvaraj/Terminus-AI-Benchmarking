variable "cluster_name" { type = string default = "regulated-platform" }
variable "vpc_id" { type = string default = "vpc-0feedface" }
variable "private_subnet_ids" { type = list(string) default = ["subnet-private-a", "subnet-private-b", "subnet-private-c"] }
variable "public_subnet_ids" { type = list(string) default = ["subnet-public-a", "subnet-public-b", "subnet-public-c"] }
