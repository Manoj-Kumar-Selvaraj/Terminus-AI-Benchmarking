#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from infra.modules.ec2.module import ModuleError, render, validate_config

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ["plan", "apply", "validate"]:
        p = sub.add_parser(n)
        p.add_argument(
            "--config", default=str(ROOT / "infra/envs/prod/ec2_config.json")
        )
        p.add_argument("--prior-state")
        p.add_argument("--out")
        p.add_argument("--state", default=str(ROOT / "state/ec2_state.json"))
    a = ap.parse_args()
    try:
        c = load(a.config)
        prior = load(a.prior_state) if a.prior_state else None
        if a.cmd == "validate":
            validate_config(c)
            res = {"valid": True, "environment": c.get("environment")}
        else:
            res = render(c, prior)
            if a.cmd == "apply":
                write(a.state, res)
        if a.out:
            write(a.out, res)
        else:
            print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    except ModuleError as e:
        res = {"valid": False, "error": str(e)}
        if a.out:
            write(a.out, res)
        else:
            print(json.dumps(res, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
