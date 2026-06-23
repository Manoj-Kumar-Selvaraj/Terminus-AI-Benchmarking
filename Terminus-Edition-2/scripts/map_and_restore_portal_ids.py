#!/usr/bin/env python3
"""Download portal submissions, map IDs to folder names, restore missing local tasks."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT.parent
TE2 = ROOT
STB = "/root/.local/bin/stb"
OUT = TE2 / "Revision-ChatGpt" / "needs_revision_pulls"
MANIFEST = OUT / "portal_ids_manifest.tsv"
MAPPED_FILE = TE2 / "needs_revision_mapped.txt"
LOG = OUT / "map_restore.log"
RESOLVED = OUT / "unmapped_resolved.tsv"

FITNESS_FOLDER = "go-fitness-class-refund-matcher"
KNOWN_FITNESS_IDS = {
    "78816498-a2d8-41ae-acd8-d42d80405961",
    "57f23c91-035f-4b52-b6a4-bae742212e3d",
    "cdefb68f-ab0e-4909-be1d-3fa153b88a4a",
    "529e2a84-f140-4036-98c2-64f45fa72f31",
    "02ce0a54-ea1c-4339-ab60-f8dcb36411d8",
    "4375ed22-f2cf-457a-8e84-223859fcb2d2",
}

ZIP_RE = re.compile(r"Found submission file: (.+?)(?:_\d{8}[^/\s]*)?\.zip", re.I)
EXTRACT_RE = re.compile(r"Extracted to (.+?)(?:\.\.\.|$)", re.M)


def log(msg: str) -> None:
    line = msg.rstrip() + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


def read_manifest() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def write_manifest(rows: list[tuple[str, str, str]]) -> None:
    lines = ["# submission_id\tlocal_folder\tstatus\n"]
    lines.extend(f"{sid}\t{folder}\t{status}\n" for sid, folder, status in rows)
    MANIFEST.write_text("".join(lines), encoding="utf-8")


def append_mapped(sid: str, folder: str) -> None:
    text = MAPPED_FILE.read_text(encoding="utf-8")
    if sid in text:
        return
    with MAPPED_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{sid}\t{folder}\n")


def find_existing_extract(folder: str) -> Path | None:
    matches = sorted(PORTFOLIO.glob(f"{folder}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in matches:
        if p.is_dir() and (p / "task.toml").is_file():
            return p
    return None


def download(sid: str) -> tuple[str, Path | None]:
    try:
        proc = subprocess.run(
            [STB, "submissions", "download", sid],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT download {sid} (300s) — will retry extract from disk if present")
        return "", None
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        log(f"FAIL download {sid}: {out[-500:]}")
        return "", None
    m = ZIP_RE.search(out)
    folder = m.group(1) if m else ""
    em = EXTRACT_RE.search(out)
    extract = Path(em.group(1).strip()) if em else None
    if folder and not extract:
        extract = find_existing_extract(folder)
    return folder, extract


def restore(folder: str, extract: Path) -> bool:
    dest = TE2 / folder
    if dest.is_dir() and (dest / "task.toml").is_file():
        log(f"  skip restore (exists): {dest}")
        return False
    if not extract or not extract.is_dir():
        log(f"  no extract dir for {folder}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(extract, dest, ignore=shutil.ignore_patterns(".snorkel_config"))
    log(f"  restored -> {dest}")
    return True


def classify(folder: str, sid: str) -> str:
    if sid in KNOWN_FITNESS_IDS or folder == FITNESS_FOLDER:
        return "FITNESS_SKIP"
    if (TE2 / folder).is_dir() and (TE2 / folder / "task.toml").is_file():
        return "LOCAL_OK"
    if folder and folder != "-":
        return "NO_LOCAL_FOLDER"
    return "UNMAPPED"


def load_resolved() -> list[tuple[str, str, str, str]]:
    if not RESOLVED.is_file():
        return []
    rows: list[tuple[str, str, str, str]] = []
    for line in RESOLVED.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def save_resolved(resolved: list[tuple[str, str, str, str]]) -> None:
    RESOLVED.write_text(
        "# submission_id\tfolder\tstatus\tnote\n"
        + "\n".join(f"{a}\t{b}\t{c}\t{d}" for a, b, c, d in resolved)
        + "\n",
        encoding="utf-8",
    )


def process_one(
    sid: str, old_folder: str, old_status: str
) -> tuple[str, str, str, str]:
    folder = old_folder if old_folder not in ("", "-") else ""
    extract: Path | None = None

    if not folder:
        folder, extract = download(sid)
        log(f"  download -> {folder or '?'}")
    else:
        extract = find_existing_extract(folder)
        if not extract and not (TE2 / folder).is_dir():
            new_folder, extract = download(sid)
            if new_folder:
                folder = new_folder
            log(f"  re-download -> {folder or '?'}")

    if folder:
        if extract and not (TE2 / folder).is_dir():
            restore(folder, extract)
        elif not extract:
            extract = find_existing_extract(folder)
            if extract:
                restore(folder, extract)

    status = classify(folder, sid) if folder else "UNMAPPED"
    if folder and folder != "-":
        append_mapped(sid, folder)
    note = "local_ok" if (TE2 / folder).is_dir() else "no_restore"
    return sid, folder or "-", status, note


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rows = read_manifest()
    targets = [
        (i, sid, folder, status)
        for i, (sid, folder, status) in enumerate(rows)
        if status in ("UNMAPPED", "NO_LOCAL_FOLDER")
    ]
    log(f"Processing {len(targets)} submissions (UNMAPPED + NO_LOCAL_FOLDER)")
    resolved = load_resolved()
    done_ids = {r[0] for r in resolved}

    for n, (i, sid, old_folder, old_status) in enumerate(targets):
        if sid in done_ids:
            log(f"\n[{n + 1}/{len(targets)}] {sid} — skip (already in resolved)")
            continue
        log(f"\n[{n + 1}/{len(targets)}] {sid} ({old_status})")
        entry = process_one(sid, old_folder, old_status)
        resolved.append(entry)
        rows[i] = (entry[0], entry[1], entry[2])
        write_manifest(rows)
        save_resolved(resolved)
        log(f"  -> {entry[1]} [{entry[2]}] (manifest saved)")

    from collections import Counter

    c = Counter(r[2] for r in rows)
    log(f"\nDone. Manifest status counts: {dict(c)}")
    log(f"Resolved: {RESOLVED}")


if __name__ == "__main__":
    main()
