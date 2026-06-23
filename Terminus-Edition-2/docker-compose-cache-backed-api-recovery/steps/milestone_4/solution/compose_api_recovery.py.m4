#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


class SimError(Exception):
    pass


def load(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text())


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def result(out, obj):
    Path(out).mkdir(parents=True, exist_ok=True)
    save(Path(out) / "result.json", obj)


def default_state():
    return {
        "services": {"db": "created", "cache": "created", "api": "stopped"},
        "db": {},
        "cache": {},
        "outbox": [],
        "processed_requests": [],
        "schema_version": 1,
        "app_version": "v1",
        "migration_lock": None,
    }


def cache_key(tenant, key, state):
    return (
        f"{tenant}|schema{state['schema_version']}|{state['app_version']}|{key}"
    )


def invalidate_cache_entries(cache, tenant, logical_key):
    prefix = f"{tenant}|"
    for cache_key_name in list(cache):
        if cache_key_name == logical_key:
            cache.pop(cache_key_name, None)
            continue
        if not cache_key_name.startswith(prefix):
            continue
        if cache_key_name.endswith(f"|{logical_key}"):
            cache.pop(cache_key_name, None)


def dependencies_healthy(st):
    return (
        st["services"].get("db") == "healthy"
        and st["services"].get("cache") == "healthy"
    )


def up(args):
    st = load(args.state, default_state())
    out = args.out
    try:
        if not dependencies_healthy(st):
            st["services"]["api"] = "blocked"
            save(args.state, st)
            result(out, {"status": "BLOCKED", "reason": "dependency not healthy"})
            return 2
        st["services"]["api"] = "healthy"
        save(args.state, st)
        result(out, {"status": "UP", "services": st["services"]})
        return 0
    except Exception as exc:
        result(out, {"status": "FAILED_CLOSED", "error": str(exc)})
    return 2


def request(args):
    st = load(args.state, default_state())
    out = args.out
    try:
        if st["services"].get("api") != "healthy":
            raise SimError("api not ready")
        if args.request_id in st.get("processed_requests", []):
            result(out, {"status": "DUPLICATE", "row_count": len(st["db"])})
            save(args.state, st)
            return 0
        key = cache_key(args.tenant, args.key, st)
        if args.method == "GET":
            val = st["cache"].get(key)
            if val is None:
                val = st["db"].get(f"{args.tenant}:{args.key}")
                if val is not None and st["services"].get("cache") == "healthy":
                    st["cache"][key] = val
            result(out, {"status": "OK", "value": val, "cache_key": key})
            save(args.state, st)
            return 0
        st["db"][f"{args.tenant}:{args.key}"] = args.value
        invalidate_cache_entries(st["cache"], args.tenant, args.key)
        st.setdefault("outbox", []).append(
            {
                "request_id": args.request_id,
                "tenant": args.tenant,
                "key": args.key,
                "op": "invalidate",
            }
        )
        st.setdefault("processed_requests", []).append(args.request_id)
        result(out, {"status": "OK", "written": True, "cache_key": key})
        save(args.state, st)
        return 0
    except Exception as exc:
        result(out, {"status": "FAILED_CLOSED", "error": str(exc)})
    save(args.state, st)
    return 2


def restart(args):
    st = load(args.state, default_state())
    seen = set()
    deduped = []
    for entry in st.get("outbox", []):
        if entry["request_id"] in seen:
            continue
        seen.add(entry["request_id"])
        deduped.append(entry)
        invalidate_cache_entries(st["cache"], entry["tenant"], entry["key"])
    st["outbox"] = deduped
    st["services"]["api"] = "healthy" if dependencies_healthy(st) else "blocked"
    save(args.state, st)
    result(args.out, {"status": "RESTARTED", "outbox_count": len(st["outbox"])})
    return 0


def migrate(args):
    st = load(args.state, default_state())
    try:
        if st.get("migration_lock") and st["migration_lock"] != args.holder:
            raise SimError("migration lock held")
        target_schema = int(args.target_schema)
        if (
            target_schema >= 2
            and args.app_version
            and args.app_version not in {"v2", "v3"}
        ):
            raise SimError("app version incompatible with target schema")
        st["migration_lock"] = args.holder
        st["schema_version"] = target_schema
        st["migration_lock"] = None
        save(args.state, st)
        result(args.out, {"status": "MIGRATED", "schema_version": st["schema_version"]})
        return 0
    except Exception as exc:
        result(
            args.out,
            {
                "status": "FAILED_CLOSED",
                "error": str(exc),
                "schema_version": st.get("schema_version"),
            },
        )
    save(args.state, st)
    return 2


def rollback(args):
    st = load(args.state, default_state())
    try:
        st["app_version"] = args.app_version
        save(args.state, st)
        result(
            args.out,
            {
                "status": "ROLLED_BACK",
                "app_version": st["app_version"],
                "db_count": len(st["db"]),
                "cache_count": len(st["cache"]),
            },
        )
        return 0
    except Exception as exc:
        result(args.out, {"status": "FAILED_CLOSED", "error": str(exc)})
    return 2


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for command in ["up", "restart"]:
        cmd = sub.add_parser(command)
        cmd.add_argument("--state", required=True)
        cmd.add_argument("--out", required=True)
    req = sub.add_parser("request")
    req.add_argument("--state", required=True)
    req.add_argument("--out", required=True)
    req.add_argument("--tenant", required=True)
    req.add_argument("--key", required=True)
    req.add_argument("--value", default="")
    req.add_argument("--method", choices=["GET", "PUT"], default="GET")
    req.add_argument("--request-id", default="")
    mig = sub.add_parser("migrate")
    mig.add_argument("--state", required=True)
    mig.add_argument("--out", required=True)
    mig.add_argument("--target-schema", required=True)
    mig.add_argument("--holder", default="run")
    mig.add_argument("--app-version", default="")
    rb = sub.add_parser("rollback")
    rb.add_argument("--state", required=True)
    rb.add_argument("--out", required=True)
    rb.add_argument("--app-version", required=True)
    ns = parser.parse_args()
    raise SystemExit(globals()[ns.cmd.replace("-", "_")](ns))


if __name__ == "__main__":
    main()
