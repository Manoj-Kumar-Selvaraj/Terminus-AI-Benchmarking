#!/usr/bin/env python3
"""Convert Go task Dockerfiles from debian-slim+curl to offline-safe golang base."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GOLANG_BASE = (
    "FROM golang:1.22.12-bookworm"
    "@sha256:3d699e4d15d0f8f13c9195c0632a16702b8cbdece2955af1c23b37ae5d55a253"
)

TEMPLATE = f"""{GOLANG_BASE}

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        ca-certificates=20230311+deb12u1 \\
        python3=3.11.2-1+b1 \\
        python3-pip=23.0.1+dfsg-1 \\
        tmux=3.3a-3 \\
        asciinema=2.2.0-1 \\
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/go/bin:${{PATH}}"

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \\
    && chmod +x /app/scripts/*.sh
"""


def needs_convert(text: str) -> bool:
    return "curl -fsSL" in text and "go.dev/dl" in text


def main() -> None:
    converted = []
    skipped = []
    for task_dir in sorted(ROOT.iterdir()):
        if not task_dir.is_dir() or not task_dir.name.startswith("go-"):
            continue
        dockerfile = task_dir / "environment" / "Dockerfile"
        if not dockerfile.is_file():
            continue
        text = dockerfile.read_text(encoding="utf-8")
        if not needs_convert(text):
            skipped.append(task_dir.name)
            continue
        dockerfile.write_text(TEMPLATE + "\n", encoding="utf-8")
        converted.append(task_dir.name)
    print(f"converted={len(converted)}")
    for name in converted:
        print(f"  {name}")
    print(f"skipped={len(skipped)} (already golang base or no curl go.dev)")


if __name__ == "__main__":
    main()
