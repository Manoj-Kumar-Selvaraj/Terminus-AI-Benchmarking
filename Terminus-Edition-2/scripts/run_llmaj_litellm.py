#!/usr/bin/env python3
"""Run strict Harbor-style LLMaJ quality checks via LiteLLM (Portkey OpenAI route).

Strict mode runs multiple high-end models and fails a criterion if ANY model fails it.
Default strict models: openai/gpt-5.4 + openai/claude-opus-4-7 (both via Portkey).

Usage:
  # Prefer stb-managed credentials (after: stb login && stb keys refresh)
  python scripts/run_llmaj_litellm.py go-my-task --strict

  # Or export manually:
  eval "$(stb keys show | grep '^export ')"
  python scripts/run_llmaj_litellm.py go-my-task --strict
  python scripts/run_llmaj_litellm.py --strict task-a task-b
  python scripts/run_llmaj_litellm.py --strict --models "openai/gpt-5.4,openai/claude-opus-4-7"
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import litellm

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_DIR = ROOT / "reworked-tasks-v2" / "llmaj-reports"

try:
    import harbor.cli.quality_checker as qc

    RUBRIC_PATH = Path(qc.__file__).parent / "default_rubric.toml"
except ImportError:
    RUBRIC_PATH = Path(litellm.__file__).parent.parent / "harbor" / "cli" / "quality_checker" / "default_rubric.toml"

try:
    import harbor.analyze

    CHECK_PROMPT = (Path(harbor.analyze.__file__).parent / "prompts" / "check.txt").read_text()
except Exception:
    CHECK_PROMPT = """You are reviewing a Harbor task for quality and completeness.

<file_tree>
{file_tree}
</file_tree>

Read ALL files below before judging.

Guidance:
{criteria_guidance}
{strict_addendum}
"""

CHECK_PROMPT = CHECK_PROMPT.replace("—", "-").replace("–", "-")

STRICT_ADDENDUM = """
STRICT REVIEW MODE - apply these rules in addition to the criteria above:
- When uncertain, choose FAIL rather than pass.
- Fail informative_test_structure if ANY test name, docstring, or inline comment does not match what the test actually asserts.
- Fail typos for ANY inconsistent filename, path, variable name, or config value, including intentional-looking misspellings (e.g. loadTripes) unless explicitly documented as part of the task spec in instruction.md.
- Fail anti_cheating_measures if solution/ scripts exist anywhere under steps/ (even if excluded from the Docker image).
- Fail test_deps_in_image if pytest or other verifier-only Python packages are installed in environment/Dockerfile.
- Fail behavior_in_task_description if ANY tested edge case is not explicitly stated in the relevant milestone instruction.md.
- Fail behavior_in_tests if ANY requirement in instruction.md lacks a direct test assertion.
- Do not give benefit of the doubt for partial coverage or implied behavior.
"""

STRICT_MODELS = ["openai/gpt-5.4", "openai/claude-opus-4-7"]
# Override with --models or LLMAJ_MODEL. Portkey slugs use openai/ prefix for Anthropic too.
# gpt-5.5 may be blocked on some Portkey integrations (INVALID_MODEL_NOT_ALLOWED).
NO_TEMPERATURE_SUBSTRINGS = ("claude-opus-4-7", "opus-4-7")
DEFAULT_MODEL = "openai/gpt-5.4"
SKIP_SUFFIXES = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc", ".json"}
SKIP_NAMES = {"llmaj-output.json"}
SKIP_DIR_NAMES = {".pytest_cache", "__pycache__", ".mypy_cache"}
MAX_FILE_BYTES = 120_000
FALLBACK_CRITERIA = [
    {
        "name": "behavior_in_task_description",
        "guidance": "The milestone instructions must explicitly describe every behavior that verifier tests require, including edge cases, tie-breakers, schemas, config files, and compatibility rules.",
    },
    {
        "name": "behavior_in_tests",
        "guidance": "The tests must directly assert the important behavior described in the task instructions rather than relying only on broad happy-path checks.",
    },
    {
        "name": "informative_test_structure",
        "guidance": "Tests should be organized clearly, use descriptive names and docstrings, and make failure reasons understandable without inspecting unrelated files.",
    },
    {
        "name": "anti_cheating_measures",
        "guidance": "The task should make it difficult to pass by hardcoding shipped data or precomputed outputs; verifier inputs should be generated or overwritten by tests.",
    },
    {
        "name": "structured_data_schema",
        "guidance": "Input and output schemas, file names, column names, JSON keys, and required value domains should be explicitly documented and consistently tested.",
    },
    {
        "name": "pinned_dependencies",
        "guidance": "Base images and package dependencies should be pinned enough for reproducible offline evaluation.",
    },
    {
        "name": "typos",
        "guidance": "Task files should avoid confusing typos, stale names, wrong paths, inconsistent terminology, and accidental misspellings unless explicitly part of the task contract.",
    },
    {
        "name": "tests_or_solution_in_image",
        "guidance": "The Docker image should not copy verifier tests, solution scripts, or submission-only artifacts into the runtime image.",
    },
    {
        "name": "test_deps_in_image",
        "guidance": "Verifier-only dependencies should not be baked into the runtime image unless the task convention explicitly requires that local packaging style.",
    },
    {
        "name": "hardcoded_solution",
        "guidance": "Solution scripts should repair the implementation and derive outputs by computation, not write fixed final answer files.",
    },
    {
        "name": "file_reference_mentioned",
        "guidance": "Instructions should mention the files agents must read and the output files the verifier checks.",
    },
]

REWORKED_TASKS = [
    "go-brewpub-tab-adjustment-matcher",
    "go-telecom-service-credit-matcher",
    "go-port-terminal-container-hold-release",
    "go-farmers-market-stall-refund-matcher",
    "go-veterinary-visit-credit-matcher",
    "go-arcade-token-credit-matcher",
    "go-coldchain-pallet-hold-release",
]


def load_rubric(path: Path) -> list[dict]:
    import tomllib

    if not path.exists():
        print(f"WARNING: rubric file not found at {path}; using built-in fallback criteria.", file=sys.stderr)
        return FALLBACK_CRITERIA
    return tomllib.loads(path.read_text(encoding="utf-8"))["criteria"]


def build_file_tree(task_dir: Path) -> str:
    return "\n".join(
        p.relative_to(task_dir).as_posix()
        for p in sorted(task_dir.rglob("*"))
        if p.is_file()
        and p.name not in SKIP_NAMES
        and p.suffix.lower() not in SKIP_SUFFIXES
        and not any(part in SKIP_DIR_NAMES for part in p.parts)
    )


def read_task_files(task_dir: Path) -> str:
    chunks: list[str] = []
    for path in sorted(task_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        rel = path.relative_to(task_dir).as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > MAX_FILE_BYTES:
            text = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace") + "\n... [truncated]"
        else:
            text = data.decode("utf-8", errors="replace")
        chunks.append(f"===== {rel} =====\n{text}\n")
    return "\n".join(chunks)


def build_prompt(
    task_dir: Path,
    criteria: list[dict],
    strict: bool,
) -> tuple[str, list[str]]:
    guidance = "\n".join(f"- {c['name']}: {c['guidance']}" for c in criteria)
    names = [c["name"] for c in criteria]
    file_tree = build_file_tree(task_dir)
    file_contents = read_task_files(task_dir)
    strict_addendum = STRICT_ADDENDUM if strict else ""

    prompt = CHECK_PROMPT.format_map(
        {
            "file_tree": file_tree,
            "criteria_guidance": guidance,
            "file_contents": file_contents,
            "strict_addendum": strict_addendum,
            "task_dir": str(task_dir),
        }
    )
    if "{file_contents}" not in CHECK_PROMPT:
        prompt += f"\n\n<file_contents>\n{file_contents}\n</file_contents>\n"
    if strict:
        prompt += f"\n{STRICT_ADDENDUM}\n"

    schema_hint = json.dumps(
        {"checks": {name: {"outcome": "pass", "explanation": "..."} for name in names}},
        indent=2,
    )
    prompt += (
        "\n\nReturn a single JSON object only. Each check outcome must be lowercase: "
        "pass, fail, or not_applicable.\n"
        f"{schema_hint}\n"
    )
    return prompt, names


def parse_json_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def model_skips_temperature(model: str) -> bool:
    lowered = model.lower()
    return any(tag in lowered for tag in NO_TEMPERATURE_SUBSTRINGS)


def _parse_export_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if line.startswith("export OPENAI_API_KEY="):
        return "OPENAI_API_KEY", line.split("=", 1)[1].strip().strip('"').strip("'")
    if line.startswith("export OPENAI_BASE_URL="):
        return "OPENAI_BASE_URL", line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_portkey_credentials() -> tuple[str, str]:
    """Resolve Portkey credentials from env, stb config, or `stb keys show`."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    api_base = os.environ.get("OPENAI_BASE_URL", "https://api.portkey.ai/v1").strip()
    if api_key:
        return api_key, api_base or "https://api.portkey.ai/v1"

    config_path = Path.home() / ".config" / "stb" / "config.ini"
    if config_path.is_file():
        config = configparser.ConfigParser()
        config.read(config_path)
        if "portkey" in config:
            pk = config["portkey"].get("api_key", "").strip()
            base = config["portkey"].get("gateway_url", "https://api.portkey.ai/v1").strip()
            if pk:
                return pk, base or "https://api.portkey.ai/v1"

    stb_bin = shutil.which("stb")
    if stb_bin:
        proc = subprocess.run(
            [stb_bin, "keys", "show"],
            capture_output=True,
            text=True,
            check=False,
        )
        show_key = ""
        show_base = "https://api.portkey.ai/v1"
        for line in proc.stdout.splitlines():
            parsed = _parse_export_line(line)
            if not parsed:
                continue
            name, value = parsed
            if name == "OPENAI_API_KEY":
                show_key = value
            else:
                show_base = value
        if show_key:
            return show_key, show_base

    raise RuntimeError(
        "No Portkey credentials found. Run: stb login && stb keys refresh\n"
        "Or export manually: eval \"$(stb keys show | grep '^export ')\""
    )


def call_model(model: str, prompt: str) -> dict:
    api_key, api_base = load_portkey_credentials()

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "api_key": api_key,
        "api_base": api_base,
    }
    if not model_skips_temperature(model):
        kwargs["temperature"] = 0

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise RuntimeError(f"{model} returned empty content")
            return parse_json_response(content)
        except json.JSONDecodeError as exc:
            last_error = exc
            kwargs.pop("response_format", None)
        except Exception as exc:
            last_error = exc
            if "temperature" in str(exc).lower() and "temperature" in kwargs:
                kwargs.pop("temperature", None)
                continue
            if "invalid api key" in str(exc).lower() or "authenticationerror" in type(exc).__name__.lower():
                raise RuntimeError(
                    "Portkey rejected the AI credentials (401 Invalid API Key).\n"
                    "Your stored stb credentials are expired and refresh is blocked.\n"
                    "Ask Snorkel admin to reset your key refresh limit, then run:\n"
                    "  stb keys refresh\n"
                    "  stb keys verify\n"
                    "  python3.11 scripts/run_llmaj_litellm.py --strict <task>"
                ) from exc
            raise
    raise RuntimeError(f"{model} failed to return valid JSON: {last_error}") from last_error


def merge_results(model_results: dict[str, dict], criterion_names: list[str]) -> dict:
    merged: dict[str, dict] = {}
    for name in criterion_names:
        outcomes = []
        explanations = []
        for model, result in model_results.items():
            checks = result.get("checks", result)
            item = checks.get(name, {})
            outcome = str(item.get("outcome", "unknown")).lower()
            expl = str(item.get("explanation", ""))
            outcomes.append(outcome)
            explanations.append(f"[{model}] {outcome.upper()}: {expl}")
        if any(o == "fail" for o in outcomes):
            final = "fail"
        elif all(o in {"pass", "not_applicable"} for o in outcomes) and any(o == "pass" for o in outcomes):
            final = "pass"
        elif all(o == "not_applicable" for o in outcomes):
            final = "not_applicable"
        else:
            final = "fail"
        merged[name] = {
            "outcome": final,
            "explanation": " | ".join(explanations),
            "by_model": {
                model: (model_results[model].get("checks", model_results[model]).get(name, {}))
                for model in model_results
            },
        }
    return merged


def run_task(
    task_dir: Path,
    models: list[str],
    strict: bool,
    out_path: Path | None,
) -> int:
    if not task_dir.is_dir():
        print(f"SKIP missing task dir: {task_dir}", file=sys.stderr)
        return 2

    criteria = load_rubric(RUBRIC_PATH)
    criterion_names = [c["name"] for c in criteria]
    prompt, _ = build_prompt(task_dir, criteria, strict)

    model_results: dict[str, dict] = {}
    for model in models:
        print(f"  -> {model} ...", flush=True)
        model_results[model] = call_model(model, prompt)

    merged = merge_results(model_results, criterion_names)
    report = {
        "task": task_dir.name,
        "strict": strict,
        "models": models,
        "checks": merged,
    }

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    passed = failed = na = 0
    print(f"\n=== {task_dir.name} ({'STRICT' if strict else 'standard'}) ===")
    for name in criterion_names:
        item = merged[name]
        outcome = item["outcome"]
        mark = {"pass": "PASS", "fail": "FAIL", "not_applicable": "N/A"}.get(outcome, outcome.upper())
        if outcome == "pass":
            passed += 1
        elif outcome == "fail":
            failed += 1
        else:
            na += 1
        print(f"\n[{mark}] {name}")
        for model in models:
            sub = item["by_model"][model]
            sub_out = str(sub.get("outcome", "?")).upper()
            sub_expl = sub.get("explanation", "")
            print(f"  {model}: {sub_out} - {sub_expl[:200]}{'...' if len(sub_expl) > 200 else ''}")

    print(f"\nSummary: {passed} pass, {failed} fail, {na} n/a")
    if out_path:
        print(f"Report: {out_path}")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict LLMaJ checks via LiteLLM/Portkey")
    parser.add_argument("tasks", nargs="*", help="Task directory names or paths")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict rubric + dual high-end models (gpt-5.4 + claude-opus-4-7)",
    )
    parser.add_argument(
        "--reworked",
        action="store_true",
        help=f"Run all reworked tasks: {', '.join(REWORKED_TASKS)}",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated LiteLLM models (overrides defaults)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for JSON reports",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    strict = args.strict

    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    elif strict:
        models = STRICT_MODELS
    else:
        models = [os.environ.get("LLMAJ_MODEL", DEFAULT_MODEL)]

    task_dirs: list[Path] = []
    if args.reworked:
        task_dirs.extend(ROOT / name for name in REWORKED_TASKS)
    for item in args.tasks:
        p = Path(item)
        task_dirs.append(p if p.is_dir() else ROOT / item)

    if not task_dirs:
        print("Provide task names or use --reworked", file=sys.stderr)
        return 2

    exit_code = 0
    for task_dir in task_dirs:
        task_dir = task_dir.resolve()
        print(f"\nChecking {task_dir.name} with {len(models)} model(s)...", flush=True)
        out_path = args.report_dir / f"{task_dir.name}{'_strict' if strict else ''}_llmaj.json"
        code = run_task(task_dir, models, strict, out_path)
        if code != 0:
            exit_code = code

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
