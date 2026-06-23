#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
chmod +x ./run_task_revision.sh

for task in terraform-aws-eks-jenkins-controller-fleet-recovery terraform-aws-eks-addons-irsa-upgrade-recovery; do
	echo "=== $task ==="
	SKIP_REPLACE=1 ZIP_EVEN_IF_ORACLE_FAIL=1 ./run_task_revision.sh "$task"
done
