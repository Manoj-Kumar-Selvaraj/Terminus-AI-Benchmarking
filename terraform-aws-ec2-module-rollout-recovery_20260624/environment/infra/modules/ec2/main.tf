resource "aws_launch_template" "this" {}
resource "aws_autoscaling_group" "this" {}
resource "aws_security_group" "instance" {}
resource "aws_iam_role" "instance" {}
resource "aws_iam_role_policy" "instance" {}
resource "aws_ebs_volume" "data" {}
resource "aws_volume_attachment" "data" {}
resource "aws_cloudwatch_log_group" "rollout" {}
