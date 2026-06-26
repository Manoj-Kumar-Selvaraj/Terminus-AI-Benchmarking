#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
cp /steps/milestone_5/solution/module.go "${APP_DIR}/infra/modules/ec2/module.go"
gofmt -w "${APP_DIR}/infra/modules/ec2/module.go"
(cd "${APP_DIR}" && go build ./cmd/ec2sim)
cat > "${APP_DIR}/infra/modules/ec2/state_migrations.tf" <<'TF'
moved {
  from = aws_launch_template.payments
  to   = aws_launch_template.this
}

moved {
  from = aws_autoscaling_group.payments
  to   = aws_autoscaling_group.this
}

moved {
  from = aws_security_group.payments_instance
  to   = aws_security_group.instance
}

moved {
  from = aws_iam_role.payments_instance
  to   = aws_iam_role.instance
}

moved {
  from = aws_ebs_volume.payments_data
  to   = aws_ebs_volume.data
}

moved {
  from = aws_volume_attachment.payments_data
  to   = aws_volume_attachment.data
}
TF
