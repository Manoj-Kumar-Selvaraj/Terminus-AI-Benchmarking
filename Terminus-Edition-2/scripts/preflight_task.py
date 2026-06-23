#!/usr/bin/env python3
"""Local structural preflight (same checks as terminus2_cli.sh preflight)."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def run_preflight(task_dir: Path) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    def err(msg: str) -> None:
        errors.append(msg)

    def warn(msg: str) -> None:
        warnings.append(msg)

    def require(path: str) -> None:
        if not (task_dir / path).exists():
            err(f"missing required path: {path}")

    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        err("missing required path: task.toml")
        data: dict = {}
    else:
        raw_toml = toml_path.read_text(encoding="utf-8")
        try:
            import tomllib

            data = tomllib.loads(raw_toml)
        except ModuleNotFoundError:
            data = {}
            current = data
            current_array_item = None

            def parse_value(value: str):
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    return value[1:-1]
                if value.startswith("[") and value.endswith("]"):
                    body = value[1:-1].strip()
                    if not body:
                        return []
                    return [parse_value(part.strip()) for part in body.split(",") if part.strip()]
                if value.lower() in {"true", "false"}:
                    return value.lower() == "true"
                try:
                    if "." in value:
                        return float(value)
                    return int(value)
                except ValueError:
                    return value

            for line in raw_toml.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                if line == "[[steps]]":
                    data.setdefault("steps", []).append({})
                    current = data["steps"][-1]
                    current_array_item = current
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    if section.startswith("steps.") and current_array_item is not None:
                        _, sub = section.split(".", 1)
                        current_array_item.setdefault(sub, {})
                        current = current_array_item[sub]
                    else:
                        current = data
                        for part in section.split("."):
                            current = current.setdefault(part, {})
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    current[key.strip()] = parse_value(value)

    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    milestones = int(metadata.get("number_of_milestones", -1))

    required_meta = [
        "author_name",
        "author_email",
        "difficulty",
        "category",
        "subcategories",
        "number_of_milestones",
        "codebase_size",
        "languages",
        "tags",
        "expert_time_estimate_min",
        "junior_time_estimate_min",
    ]
    if data.get("version") != "2.0":
        err('task.toml version must be "2.0"')
    for key in required_meta:
        if key not in metadata:
            err(f"task.toml missing [metadata].{key}")

    env = data.get("environment", {}) if isinstance(data, dict) else {}
    for key in ["build_timeout_sec", "cpus", "memory_mb", "storage_mb"]:
        if key not in env:
            err(f"task.toml missing [environment].{key}")

    require("environment")
    if not (task_dir / "environment" / "Dockerfile").exists() and not (
        task_dir / "environment" / "docker-compose.yaml"
    ).exists():
        err("environment must contain Dockerfile or docker-compose.yaml")

    if milestones <= 0:
        require("instruction.md")
        require("solution/solve.sh")
        require("tests/test.sh")
        require("tests/test_outputs.py")
    else:
        if milestones < 2:
            err("milestone tasks must have at least 2 milestones")
        for forbidden in ["instruction.md", "solution", "tests"]:
            if (task_dir / forbidden).exists():
                err(f"milestone task must not include root-level {forbidden}")
        steps = data.get("steps", [])
        if len(steps) != milestones:
            err("number_of_milestones must equal the number of [[steps]] blocks")
        for i in range(1, milestones + 1):
            base = f"steps/milestone_{i}"
            require(f"{base}/instruction.md")
            require(f"{base}/tests/test.sh")
            py_test = f"{base}/tests/test_m{i}.py"
            rb_test = f"{base}/tests/test_m{i}.rb"
            if not (task_dir / py_test).exists() and not (task_dir / rb_test).exists():
                err(f"missing required path: {py_test} (or {rb_test})")
            require(f"{base}/solution/solve.sh")
            require(f"{base}/solution/solve{i}.sh")

    instruction_paths = []
    if milestones <= 0:
        instruction_paths.append(task_dir / "instruction.md")
    else:
        instruction_paths.extend(
            task_dir / "steps" / f"milestone_{i}" / "instruction.md" for i in range(1, milestones + 1)
        )

    for path in instruction_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "canary" in text.lower():
            err(f"{path.relative_to(task_dir)} contains a canary string")

    docker_text = ""
    for docker_path in [task_dir / "environment" / "Dockerfile", task_dir / "environment" / "docker-compose.yaml"]:
        if docker_path.exists():
            docker_text += "\n" + docker_path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"\bCOPY\s+(tests|solution|steps)/", docker_text):
        err("Docker environment appears to copy tests, solution, or steps into the image")

    excluded_env_names = {"Dockerfile", "docker-compose.yaml", "docker-compose.yml"}
    env_files = (
        [
            p
            for p in (task_dir / "environment").rglob("*")
            if p.is_file() and p.name not in excluded_env_names
        ]
        if (task_dir / "environment").exists()
        else []
    )
    codebase_size = metadata.get("codebase_size")
    if codebase_size == "small" and len(env_files) < 20:
        err(
            f"codebase_size is small but environment has only {len(env_files)} files "
            "(excluding Dockerfile/docker-compose)"
        )

    print(f"[{task_dir.name}] Environment file count: {len(env_files)} (harbor-style)")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"[{task_dir.name}] Preflight passed.")
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: preflight_task.py <task-dir> [task-dir ...]", file=sys.stderr)
        raise SystemExit(2)
    rc = 0
    for arg in sys.argv[1:]:
        task_dir = Path(arg).resolve()
        if not task_dir.is_dir():
            print(f"ERROR: not a directory: {task_dir}", file=sys.stderr)
            rc = 1
            continue
        if run_preflight(task_dir) != 0:
            rc = 1
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
