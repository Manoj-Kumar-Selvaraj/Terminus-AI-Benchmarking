from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim.loader import find_by_name, load_manifest_bundle
from sim.ledger import active_billing_window, build_ledger_artifact_name
from sim.rbac import (
    collect_role_permissions,
    evaluate_configmap_read,
    has_wildcard_permission,
    permissions_are_minimal,
    permissions_cover_workflow,
    resolve_role_for_service_account,
)
from sim.scheduler import cronjob_concurrency_policy, cronjob_service_account, simulate_overlapping_runs


APP_ROOT = Path("/app")
MANIFEST_DIR = APP_ROOT / "manifests"
SIM_CONFIG = APP_ROOT / "sim" / "config.json"


def load_sim_config() -> dict:
    return json.loads(SIM_CONFIG.read_text(encoding="utf-8"))


def run_bundle_checks(manifest_dir: Path | None = None) -> dict:
    manifest_dir = manifest_dir or MANIFEST_DIR
    cfg = load_sim_config()
    bundle = load_manifest_bundle(manifest_dir)
    namespace = cfg["namespace"]
    sa_name = cfg["service_account"]
    configmap_name = cfg["configmap"]
    cronjob_name = cfg["cronjob"]

    configmap = find_by_name(bundle["configmaps"], configmap_name, namespace)
    cronjob = find_by_name(bundle["cronjobs"], cronjob_name, namespace)
    if configmap is None or cronjob is None:
        raise RuntimeError("required manifests missing from bundle")

    rbac_result = evaluate_configmap_read(sa_name, namespace, configmap_name, bundle)
    cron_sa, cron_ns = cronjob_service_account(cronjob)
    sa_chain_ok = cron_sa == sa_name and cron_ns == namespace and rbac_result["authorized"]

    overlap = simulate_overlapping_runs(
        cronjob,
        first_start_minute=cfg["overlap"]["first_start_minute"],
        second_start_minute=cfg["overlap"]["second_start_minute"],
        job_duration_minutes=cfg["overlap"]["job_duration_minutes"],
        billing_window_id=cfg["overlap"]["billing_window_id"],
    )

    role = resolve_role_for_service_account(sa_name, namespace, bundle["rolebindings"], bundle["roles"])
    permissions = collect_role_permissions(role)
    window_id = active_billing_window(configmap)
    artifact_name = build_ledger_artifact_name(configmap, window_id)

    return {
        "rbac": rbac_result,
        "service_account_chain": {
            "cronjob_service_account": cron_sa,
            "expected_service_account": sa_name,
            "matches": cron_sa == sa_name,
            "configmap_read_ok": rbac_result["authorized"],
            "workflow_ready": sa_chain_ok,
        },
        "overlap": overlap,
        "publication": {
            "active_window_id": window_id,
            "artifact_name": artifact_name,
            "single_publication_per_window": overlap["single_publication_per_window"],
        },
        "least_privilege": {
            "bound_role": None if role is None else role.get("metadata", {}).get("name"),
            "permissions": permissions,
            "has_wildcards": has_wildcard_permission(permissions),
            "covers_workflow": permissions_cover_workflow(permissions),
            "is_minimal": permissions_are_minimal(permissions),
            "concurrency_policy": cronjob_concurrency_policy(cronjob),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline invoice batch manifest simulator")
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    parser.add_argument("--scenario", choices=["all", "rbac", "overlap", "least_privilege"], default="all")
    args = parser.parse_args()

    results = run_bundle_checks(Path(args.manifest_dir))
    if args.scenario != "all":
        results = {args.scenario: results[args.scenario]}
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
