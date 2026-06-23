#!/usr/bin/env python3
"""List NEEDS_REVISION submissions (exclude go-fitness duplicates) — live streaming pull."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "bfe79c33-8ab0-4061-9849-08d3207c9927"
STB = "/root/.local/bin/stb"
OUTPUT_DIR = ROOT / "Revision-ChatGpt" / "needs_revision_pulls"
CACHE = Path("/tmp/stb_list.txt")

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}

KNOWN_IDS: dict[str, str] = {
    "d567814d-307d-48a2-bb01-be833ea1108e": "ruby-courier-cod-remittance-reconciler",
}

FITNESS_IDS = {
    "78816498-a2d8-41ae-acd8-d42d80405961",
    "57f23c91-035f-4b52-b6a4-bae742212e3d",
    "cdefb68f-ab0e-4909-be1d-3fa153b88a4a",
    "529e2a84-f140-4036-98c2-64f45fa72f31",
    "02ce0a54-ea1c-4339-ab60-f8dcb36411d8",
}
STATES = ("NEEDS_REVISION", "EVALUATION_PENDING", "REVIEW_PENDING", "ACCEPTED")
UUID_RE = re.compile(
    r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
)


def load_mapped() -> dict[str, str]:
    mapped: dict[str, str] = {}
    path = ROOT / "needs_revision_mapped.txt"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                sid, plat = line.split(None, 1)
                mapped[sid] = ALIASES.get(plat, plat)
    for sid, folder in KNOWN_IDS.items():
        mapped.setdefault(sid, folder)
    return mapped


def parse_line(line: str) -> tuple[str, str, str] | None:
    if not UUID_RE.search(line):
        return None
    sid = UUID_RE.search(line).group(1)
    state = "UNKNOWN"
    for s in STATES:
        if s in line:
            state = s
            break
    folder = ""
    parts = [p.strip() for p in line.split("│")]
    if len(parts) >= 5:
        folder = parts[3].strip()
    return sid, folder, state


def resolve_folder(sid: str, portal_folder: str, mapped: dict[str, str]) -> str:
    if sid in mapped:
        return mapped[sid]
    if portal_folder and portal_folder not in ("", "..."):
        name = portal_folder.rstrip(".").strip()
        if name.endswith("..."):
            name = name[:-3]
        for d in ROOT.iterdir():
            if d.is_dir() and d.name.startswith(name):
                return d.name
    return ""


def stb_command() -> list[str]:
    return [STB, "submissions", "list", "-p", PROJECT, "--show-folder-names"]


def iter_stb_lines() -> subprocess.Popen[str]:
    """Start stb list; caller reads stdout line-by-line."""
    return subprocess.Popen(
        stb_command(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )


def iter_cached_lines(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield line


class LiveWriter:
    def __init__(self, stamp: str, mapped: dict[str, str]) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.stamp = stamp
        self.mapped = mapped
        self.raw_path = OUTPUT_DIR / f"stb_list_raw_{stamp}.txt"
        self.manifest_path = OUTPUT_DIR / f"manifest_{stamp}.txt"
        self.orphans_path = OUTPUT_DIR / f"orphans_{stamp}.txt"
        self.summary_path = OUTPUT_DIR / f"summary_{stamp}.txt"

        self.state_counts: dict[str, int] = {}
        self.nr_total = 0
        self.nr_fitness = 0
        self.nr_scope = 0
        self.local_count = 0

        self._raw = self.raw_path.open("w", encoding="utf-8", buffering=1)
        self._manifest = self.manifest_path.open("w", encoding="utf-8", buffering=1)
        self._orphans = self.orphans_path.open("w", encoding="utf-8", buffering=1)
        self._cache = CACHE.open("w", encoding="utf-8", buffering=1)

        self._manifest.write("# Non-fitness NEEDS_REVISION queue (live)\n")
        self._manifest.write(f"# Generated: {stamp}\n")
        self._manifest.write(f"# Project: {PROJECT}\n")
        self._manifest.write(f"# Raw list: {self.raw_path.name}\n\n")
        self._manifest.flush()

        self._orphans.write(f"# Orphans — NEEDS_REVISION but no local folder ({stamp})\n\n")
        self._orphans.flush()

        print(f"Live raw:      {self.raw_path}", flush=True)
        print(f"Live manifest: {self.manifest_path}", flush=True)
        print(f"Live orphans:  {self.orphans_path}", flush=True)

    def close(self) -> None:
        self._raw.close()
        self._manifest.close()
        self._orphans.close()
        self._cache.close()

        summary = (
            f"# Pull summary {self.stamp}\n"
            f"project={PROJECT}\n"
            f"states={self.state_counts}\n"
            f"needs_revision_total={self.nr_total}\n"
            f"needs_revision_fitness={self.nr_fitness}\n"
            f"needs_revision_scope={self.nr_scope}\n"
            f"mapped_local={self.local_count}\n"
            f"orphans={self.nr_scope - self.local_count}\n"
            f"raw={self.raw_path}\n"
            f"manifest={self.manifest_path}\n"
            f"orphans={self.orphans_path}\n"
        )
        self.summary_path.write_text(summary, encoding="utf-8")
        print(f"\nSummary:       {self.summary_path}", flush=True)
        print(
            f"NEEDS_REVISION total={self.nr_total} fitness={self.nr_fitness} "
            f"scope={self.nr_scope} mapped_local={self.local_count} "
            f"orphans={self.nr_scope - self.local_count}",
            flush=True,
        )

    def ingest(self, line: str) -> None:
        sys.stdout.write(line)
        sys.stdout.flush()

        self._raw.write(line)
        self._raw.flush()
        self._cache.write(line)
        self._cache.flush()

        row = parse_line(line)
        if not row:
            return
        sid, portal_folder, state = row
        self.state_counts[state] = self.state_counts.get(state, 0) + 1

        if state != "NEEDS_REVISION":
            return

        self.nr_total += 1
        if sid in FITNESS_IDS:
            self.nr_fitness += 1
            print(f"[skip fitness] {sid} {portal_folder}", flush=True)
            return

        self.nr_scope += 1
        folder = resolve_folder(sid, portal_folder, self.mapped)
        local = bool(folder and (ROOT / folder).is_dir())
        if local:
            self.local_count += 1
        tag = "" if local else " # ORPHAN"
        manifest_line = f"{sid}\t{folder or 'UNKNOWN'}\t{portal_folder or '-'}{tag}\n"
        self._manifest.write(manifest_line)
        self._manifest.flush()
        print(f"[NEEDS_REVISION] {manifest_line.rstrip()}", flush=True)

        if not local:
            orphan_line = f"{sid}\t{portal_folder or '-'}\n"
            self._orphans.write(orphan_line)
            self._orphans.flush()


def stream_from_cache(writer: LiveWriter, cache: Path) -> None:
    print(f"Replaying cached list: {cache}", flush=True)
    for line in iter_cached_lines(cache):
        writer.ingest(line if line.endswith("\n") else line + "\n")


def stream_from_portal(writer: LiveWriter) -> None:
    timeout = int(os.environ.get("STB_LIST_TIMEOUT", "0"))  # 0 = no timeout
    print("Fetching portal list (live stream; rows recorded as they arrive)...", flush=True)
    proc = iter_stb_lines()
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            writer.ingest(line if line.endswith("\n") else line + "\n")
    finally:
        try:
            proc.wait(timeout=timeout if timeout > 0 else None)
        except subprocess.TimeoutExpired:
            proc.kill()
            print("\nWarning: stb list timed out; partial files kept.", flush=True)
        if proc.returncode not in (0, None) and proc.returncode != 0:
            print(f"Warning: stb list exited {proc.returncode}; partial files kept.", flush=True)


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mapped = load_mapped()
    writer = LiveWriter(stamp, mapped)
    try:
        if os.environ.get("STB_LIST_CACHE") == "1" and CACHE.is_file():
            stream_from_cache(writer, CACHE)
        else:
            stream_from_portal(writer)
    finally:
        writer.close()


if __name__ == "__main__":
    main()
