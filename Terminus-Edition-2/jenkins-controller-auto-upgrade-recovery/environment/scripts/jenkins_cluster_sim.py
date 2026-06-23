#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))


def load_json(rel, default=None):
    p = APP / rel
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(str(p))
    with p.open() as f:
        return json.load(f)


def write_json(rel, obj):
    p = APP / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def version_tuple(v):
    parts = []
    for piece in re.split(r"[.v_-]", str(v)):
        if piece.isdigit():
            parts.append(int(piece))
            if len(parts) == 3:
                break
    return tuple(parts + [0] * (3 - len(parts)))


def plugin_version_ok(actual, required):
    return version_tuple(actual) >= version_tuple(required)


def xml_ok(rel):
    try:
        ET.parse(APP / rel)
        return True
    except Exception:
        return False


def file_contains(rel, text):
    p = APP / rel
    return p.exists() and text in p.read_text(errors="ignore")


def diagnose():
    checks = []
    errors = []
    cluster = load_json("cluster/controller_deployment.json")
    contract = load_json("config/version_contract.json")
    target = cluster.get("jenkins_version")
    required = contract["versions"].get(target, {}).get("required_java")
    java_major = int(cluster.get("java_major", 0))
    image = cluster.get("controller_image", "")
    runtime_ok = bool(required) and java_major >= required and f"jdk{required}" in image
    checks.append(
        {
            "name": "runtime",
            "ok": runtime_ok,
            "target": target,
            "required_java": required,
            "java_major": java_major,
        }
    )
    if not runtime_ok:
        errors.append(
            "Target Jenkins runtime is not compatible with the configured Java major version"
        )
        return {
            "phase": "RUNTIME_INCOMPATIBLE",
            "ready": False,
            "checks": checks,
            "errors": errors,
        }

    state = load_json("jenkins_home/controller_state.json", {})
    lock = APP / "jenkins_home/UPGRADE.lock"
    home_ok = (
        xml_ok("jenkins_home/config.xml")
        and xml_ok("jenkins_home/credentials.xml")
        and file_contains("jenkins_home/config.xml", "<version>2.462.3</version>")
        and state.get("home_schema") == "recovered-target"
        and state.get("restored_from_snapshot")
    )
    queue_xml_ok = xml_ok("jenkins_home/queue.xml")
    lock_ok = not lock.exists()
    jobs = (
        load_json("jenkins_home/jobs.json", {"jobs": []})
        if (APP / "jenkins_home/jobs.json").exists()
        else {"jobs": []}
    )
    jobs_ok = {
        "payments-ledger/main",
        "shared-library/test",
        "platform-smoke/healthcheck",
    }.issubset(set(jobs.get("jobs", [])))
    home_all_ok = home_ok and queue_xml_ok and lock_ok and jobs_ok
    checks.append(
        {
            "name": "home_integrity",
            "ok": home_all_ok,
            "config_xml": xml_ok("jenkins_home/config.xml"),
            "queue_xml": queue_xml_ok,
            "upgrade_lock_absent": lock_ok,
            "jobs_preserved": jobs_ok,
        }
    )
    if not home_all_ok:
        errors.append("Jenkins home is not safely restored after failed upgrade boot")
        return {
            "phase": "HOME_CORRUPT",
            "ready": False,
            "checks": checks,
            "errors": errors,
        }

    plugins = load_json("jenkins_home/plugins/plugins.json")
    baseline = contract["target_plugin_baseline"]
    plugin_errors = []
    for name in contract["essential_plugins"]:
        meta = plugins.get(name)
        req = baseline[name]
        if not meta or not meta.get("enabled"):
            plugin_errors.append(f"{name}:missing-or-disabled")
        elif not plugin_version_ok(meta.get("version", "0"), req["min_version"]):
            plugin_errors.append(f"{name}:version")
        elif req["min_java"] > java_major:
            plugin_errors.append(f"{name}:java")
    checks.append({"name": "plugins", "ok": not plugin_errors, "errors": plugin_errors})
    if plugin_errors:
        errors.append(
            "Essential plugin baseline is not compatible with the recovered controller"
        )
        return {
            "phase": "PLUGIN_INCOMPATIBLE",
            "ready": False,
            "checks": checks,
            "errors": errors,
        }

    policy = load_json("cluster/auto_upgrade_policy.json")
    snapshot = policy.get("required_backup_snapshot", "")
    snapshot_exists = bool(snapshot) and (APP / "backups" / snapshot).exists()
    policy_ok = (
        policy.get("auto_upgrade_enabled") is False
        and policy.get("channel") == "pinned-lts"
        and policy.get("target_version") == target
        and policy.get("pin_target_version") is True
        and policy.get("java_preflight_required") is True
        and policy.get("backup_required") is True
        and snapshot_exists
        and policy.get("abort_on_failed_preflight") is True
        and policy.get("lock_strategy") == "clear-after-verified-restore"
    )
    checks.append(
        {"name": "upgrade_policy", "ok": policy_ok, "snapshot_exists": snapshot_exists}
    )
    if not policy_ok:
        errors.append("Upgrade automation is still unsafe for the recovered controller")
        return {
            "phase": "UNSAFE_AUTOMATION",
            "ready": False,
            "checks": checks,
            "errors": errors,
        }

    topology = load_json("cluster/topology.json")
    pods = topology.get("pods", [])
    active_rw = [
        p
        for p in pods
        if p.get("role") == "active" and p.get("mounts_home") and p.get("read_write")
    ]
    elected = [p for p in pods if p.get("elected") is True]
    service_ok = bool(elected) and topology.get("service", {}).get(
        "routes_to"
    ) == elected[0].get("name")
    fencing_ok = (
        len(active_rw) == 1
        and len(elected) == 1
        and active_rw[0].get("name") == elected[0].get("name")
        and topology.get("home_claim", {}).get("access_mode") == "ReadWriteOnce"
    )
    agents_ok = all(
        int(a.get("remoting_java_major", 0))
        >= int(contract.get("required_agent_java", 17))
        for a in topology.get("agents", [])
        if a.get("online")
    )
    queue = load_json("jenkins_home/queue.json", {"items": []})
    ids = [i.get("id") for i in queue.get("items", [])]
    queue_ok = len(ids) == len(set(ids)) and {"q-1001", "q-1002"}.issubset(set(ids))
    cluster_ok = service_ok and fencing_ok and agents_ok and queue_ok
    checks.append(
        {
            "name": "cluster_fencing",
            "ok": cluster_ok,
            "service_ok": service_ok,
            "fencing_ok": fencing_ok,
            "agents_ok": agents_ok,
            "queue_ok": queue_ok,
        }
    )
    if not cluster_ok:
        errors.append("Controller election, route, agent, or queue recovery is unsafe")
        return {
            "phase": "CLUSTER_UNSAFE",
            "ready": False,
            "checks": checks,
            "errors": errors,
        }

    return {"phase": "READY", "ready": True, "checks": checks, "errors": []}


def start():
    result = diagnose()
    out = APP / "out"
    out.mkdir(exist_ok=True)
    write_json("out/controller_diagnostics.json", result)
    if result["ready"]:
        cluster = load_json("cluster/controller_deployment.json")
        write_json(
            "out/controller_status.json",
            {
                "status": "READY",
                "cluster": cluster["cluster"],
                "deployment": cluster["deployment"],
                "jenkins_version": cluster["jenkins_version"],
                "java_major": cluster["java_major"],
                "home_claim": cluster["home_claim"],
                "timestamp": "2026-06-19T00:00:00Z",
            },
        )
        return 0
    return 2


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnose")
    d.add_argument("--json", action="store_true")
    sub.add_parser("start")
    args = ap.parse_args()
    if args.cmd == "diagnose":
        r = diagnose()
        if args.json:
            print(json.dumps(r, indent=2, sort_keys=True))
        else:
            print(r["phase"])
        return 0 if r["ready"] else 2
    if args.cmd == "start":
        return start()
    return 1


if __name__ == "__main__":
    sys.exit(main())
