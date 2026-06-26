"""Shared helpers for enterprise billing approval tests."""
import os
import subprocess
from pathlib import Path

APP = Path("/app")
MANIFEST = APP / "config" / "usage_manifest.txt"
INV = APP / "out" / "invoice_register.dat"
TRACE = APP / "out" / "approval_trace.dat"
SUMMARY = APP / "out" / "billing_summary.txt"
CHECKPOINT = APP / "out" / "checkpoint.dat"
PRIOR = APP / "config" / "prior_ledger.dat"
COMPILE_TIMEOUT = 45
RUN_TIMEOUT = 15


def fmt_amount(amount: int) -> str:
    if amount < 0:
        return f"-{abs(amount):09d}"
    return f"{amount:010d}"


def fmt_usage(account: str, batch: str, seq: str, amount: int, service: str = "SVC1") -> str:
    amount_field = fmt_amount(amount)
    line = f"U{account}{batch}{seq}{amount_field}{service}"
    assert len(amount_field) == 10, amount_field
    assert len(line) <= 52, line
    return line.ljust(52)


def parse_invoices(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line or line[0] != "I":
            continue
        rows.append(
            {
                "account_id": line[1:9],
                "invoice_no": int(line[9:19]),
                "total_cents": int(line[19:29]),
                "approval_tier": line[29:39].strip(),
                "stages": line[39:55].strip(),
                "status": line[55:63].strip(),
            }
        )
    return rows


def parse_trace(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line or line[0] != "T":
            continue
        rows.append(
            {
                "account_id": line[1:9],
                "stage": line[9:17].strip(),
                "result": line[17:25].strip(),
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


def assert_output_record_widths() -> None:
    """Verify fixed-offset invoice and trace fields remain at documented positions."""
    for raw in INV.read_text().splitlines():
        line = raw.rstrip("\n")
        if line and line[0] == "I":
            assert len(line) == 72, f"Invoice record width must be 72: {len(line)}"
            assert line[29:39].strip(), "Invoice approval_tier field missing"
            assert line[39:55].strip(), "Invoice stages field missing"
            assert line[55:63].strip(), "Invoice status field missing"
    for raw in TRACE.read_text().splitlines():
        line = raw.rstrip("\n")
        if line and line[0] == "T":
            assert len(line) == 40, f"Trace record width must be 40: {len(line)}"
            assert line[1:9].strip(), "Trace account field missing"
            assert line[9:17].strip(), "Trace stage field missing"
            assert line[17:].strip(), "Trace result field missing"


def assert_checkpoint_layout(text: str | None = None) -> None:
    """Verify the 138-byte checkpoint record matches record_layouts.md."""
    raw = text if text is not None else CHECKPOINT.read_text()
    line = raw.splitlines()[0] if raw.splitlines() else raw
    line = line.rstrip("\n")[:138]
    assert len(line) == 138, f"checkpoint must be 138 bytes, got {len(line)}"
    assert line[0:2].strip().isdigit(), "manifest file number at offset 1"
    assert line[2:8].strip().isdigit(), "record number at offset 3"
    assert line[8:16].strip(), "pending account at offset 9"
    assert line[16:26].strip().isdigit(), "pending account total at offset 17"
    assert line[26:32].strip().isdigit(), "pending usage count at offset 27"
    assert line[32:42].strip().isdigit(), "last committed invoice number at offset 33"
    assert line[42:48].strip().isdigit(), "processed row count at offset 43"
    assert line[48:54].strip().isdigit(), "total usage rows at offset 49"
    assert line[54:60].strip().isdigit(), "invoices posted at offset 55"
    assert line[60:72].strip().isdigit(), "total billed cents at offset 61"
    assert line[72:78].strip().isdigit(), "duplicate batches blocked at offset 73"
    assert line[78:80].strip().isdigit(), "pending batch count at offset 79"
    last_amt = line[80:90].strip()
    assert last_amt.lstrip("-").isdigit(), "last usage amount at offset 81"


def compile_program() -> None:
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=COMPILE_TIMEOUT)
    assert (APP / "build" / "batch").read_bytes().startswith(b"ELF")


def write_manifest(paths: list[str]) -> None:
    lines = [f"{idx:02d} {path}" for idx, path in enumerate(paths, start=1)]
    MANIFEST.write_text("\n".join(lines) + "\n")


def write_usage(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = []
    for row in rows:
        if len(row) < 52:
            row = row.ljust(52)
        assert len(row) == 52, f"bad row length {len(row)}: {row!r}"
        normalized.append(row)
    path.write_text("\n".join(normalized) + "\n")


def write_prior(rows: list[str]) -> None:
    PRIOR.write_text("\n".join(rows) + "\n")


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


def run_full(env: dict | None = None) -> tuple[list[dict], list[dict], dict[str, int]]:
    clean_outputs()
    compile_program()
    proc = run_batch(env)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    invoices = parse_invoices(INV.read_text())
    trace = parse_trace(TRACE.read_text())
    summary = parse_summary(SUMMARY.read_text())
    assert_output_record_widths()
    return invoices, trace, summary
