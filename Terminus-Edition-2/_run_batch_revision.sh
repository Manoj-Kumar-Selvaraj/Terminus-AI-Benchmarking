#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
chmod +x ./run_task_revision.sh

tasks=(
	terraform-aws-eks-jenkins-controller-fleet-recovery
	terraform-aws-eks-addons-irsa-upgrade-recovery
	terraform-aws-vpc-module-egress-recovery
	terraform-aws-ec2-module-rollout-recovery
	jenkins-controller-auto-upgrade-recovery
)

failed=()
passed=()

for task in "${tasks[@]}"; do
	echo
	echo "============================================================"
	echo "Running: $task"
	echo "============================================================"

	if SKIP_REPLACE=1 ZIP_EVEN_IF_ORACLE_FAIL=1 ./run_task_revision.sh "$task"; then
		passed+=("$task")
	else
		failed+=("$task")
	fi
done

echo
echo "BATCH SUMMARY"
echo "Passed: ${#passed[@]}"
printf '  %s\n' "${passed[@]}"
echo "Failed: ${#failed[@]}"
printf '  %s\n' "${failed[@]}"

[[ ${#failed[@]} -eq 0 ]]
