"""Shared parsing helpers for statement merge tests."""
import os
import subprocess
from pathlib import Path

APP = Path("/app")
MANIFEST = APP / "config" / "stream_manifest.txt"
CTL = APP / "out" / "control_totals.dat"
SUMMARY = APP / "out" / "merge_summary.txt"
CHECKPOINT = APP / "out" / "checkpoint.dat"
COMPILE_TIMEOUT = 45
RUN_TIMEOUT = 15


def fmt_stmt(account: str, stmt_date: str, seq: str, txn: str, amount: int, tag: str = "RUN01") -> str:
    """Build a 48-byte statement record."""
    line = (
        f"S{account}{stmt_date}{seq}{txn}{amount:010d}{tag}"
    )
    assert len(line) <= 48, line
    return line.ljust(48)


def parse_control_rows(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line or line[0] != "T":
            continue
        rows.append(
            {
                "account_id": line[1:9],
                "stmt_date": line[9:17],
                "debit_cents": int(line[17:27]),
                "credit_cents": int(line[27:37]),
                "stmt_count": int(line[37:47]),
                "status": line[47],
            }
        )
    return rows


def parse_summary(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = int(value.strip())
    return out


def assert_cobol_binary() -> None:
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert "stmt_merge.cbl" in compile_script
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program() -> None:
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=COMPILE_TIMEOUT)
    assert_cobol_binary()


def write_manifest(paths: list[str]) -> None:
    lines = []
    for idx, path in enumerate(paths, start=1):
        lines.append(f"{idx:02d} {path}")
    MANIFEST.write_text("\n".join(lines) + "\n")


def write_stream(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = []
    for row in rows:
        if len(row) < 48:
            row = row.ljust(48)
        assert len(row) == 48, f"bad row length {len(row)}: {row!r}"
        normalized.append(row)
    path.write_text("\n".join(normalized) + "\n")


def clean_outputs() -> None:
    subprocess.run(["/app/scripts/clean_outputs.sh"], check=True, cwd=APP, timeout=10)


def run_batch(env: dict | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["/app/build/batch"],
        check=False,
        cwd=APP,
        timeout=RUN_TIMEOUT,
        env=merged,
        capture_output=True,
        text=True,
    )


def run_full(env: dict | None = None) -> tuple[list[dict], dict[str, int]]:
    clean_outputs()
    compile_program()
    proc = run_batch(env)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    rows = parse_control_rows(CTL.read_text())
    summary = parse_summary(SUMMARY.read_text())
    return rows, summary
