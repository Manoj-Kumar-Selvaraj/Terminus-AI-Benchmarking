#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infra.modules.ec2.module import ModuleError, render, validate_config



def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def repair_journal(path):
    journal = Path(path)
    if not journal.exists():
        return [], {"truncated_tail": False, "preserved_records": 0}
    raw = journal.read_text(encoding="utf-8")
    lines = raw.splitlines()
    records = []
    truncated = False
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if index != len(lines) - 1:
                raise ModuleError(f"invalid interior journal record at line {index + 1}") from exc
            truncated = True
    if truncated:
        text = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records)
        journal.write_text(text, encoding="utf-8")
    return records, {"truncated_tail": truncated, "preserved_records": len(records)}


def append_journal(path, record):
    journal = Path(path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with open(journal, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def parser():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply", "validate"):
        command = sub.add_parser(name)
        command.add_argument("--config", default=str(ROOT / "infra/envs/prod/ec2_config.json"))
        command.add_argument("--prior-state")
        command.add_argument("--out")
        command.add_argument("--state", default=str(ROOT / "state/ec2_state.json"))
        command.add_argument("--journal")
    return ap


def main():
    args = parser().parse_args()
    journal_path = args.journal or (str(args.state) + ".journal.jsonl")
    try:
        config = load(args.config)
        prior = None
        if args.prior_state:
            prior = load(args.prior_state)
        elif args.cmd == "apply" and Path(args.state).exists():
            prior = load(args.state)

        _, journal_repair = repair_journal(journal_path)

        if args.cmd == "validate":
            validate_config(config)
            result = {
                "valid": True,
                "schema_version": config.get("schema_version"),
                "environment": config.get("environment"),
                "journal_repair": journal_repair,
            }
        else:
            result = render(config, prior)
            result["journal_repair"] = journal_repair
            if args.cmd == "apply":
                atomic_write(args.state, result)
                append_journal(
                    journal_path,
                    {
                        "operation_id": result.get("outputs", {}).get("rollout_operation_id"),
                        "release_manifest_sha256": result.get("release_identity", {}).get("manifest_sha256"),
                        "refresh_status": result.get("autoscaling_group", {}).get("instance_refresh", {}).get("status"),
                        "state_digest": result.get("state_digest"),
                    },
                )

        if args.out:
            atomic_write(args.out, result)
        else:
            print(json.dumps(result, indent=2, sort_keys=True))

        if args.cmd == "apply" and result.get("control_plane_response_lost"):
            return 3
        return 0
    except (ModuleError, OSError, ValueError, KeyError) as exc:
        error = {"valid": False, "error": str(exc)}
        if args.out:
            atomic_write(args.out, error)
        else:
            print(json.dumps(error, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
