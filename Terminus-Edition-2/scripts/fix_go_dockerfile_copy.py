#!/usr/bin/env python3
"""Fix Go task Dockerfiles: only COPY dirs that exist under environment/."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TASKS = [
    "go-aquarium-pass-credit-matcher",
    "go-bike-share-trip-credit-matcher",
    "go-carwash-subscription-rebate-matcher",
    "go-catering-order-adjustment-matcher",
    "go-datacenter-rack-hold-release",
    "go-device-warranty-claim-matcher",
    "go-escape-room-booking-refund-matcher",
    "go-lab-sample-chain-reassignment",
    "go-live-auction-bid-reversal-ledger",
    "go-marketplace-payout-matcher",
    "go-travel-booking-adjustment-matcher",
    "go-utility-refund-reconciler",
    "go-warehouse-pickwave-shortage-matcher",
    "go-waterpark-pass-refund-matcher",
]

RUN_BLOCK = """RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        ca-certificates=20230311+deb12u1 \\
        curl=7.88.1-10+deb12u14 \\
        python3=3.11.2-1+b1 \\
        python3-pip=23.0.1+dfsg-1 \\
        tmux=3.3a-3 \\
        asciinema=2.2.0-1 \\
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/go.tgz \\
    && echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c - \\
    && tar -C /usr/local -xzf /tmp/go.tgz \\
    && rm /tmp/go.tgz \\
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*"""

HEADER = """FROM debian:bookworm-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb

WORKDIR /app

ENV GO_VERSION=1.22.12
ENV GO_SHA256=4fa4f869b0f7fc6bb1eb2660e74657fbf04cdd290b5aef905585c86051b34d43

"""

COPY_CANDIDATES = [
    ("go.mod", "COPY go.mod /app/go.mod"),
    ("cmd", "COPY cmd/ /app/cmd/"),
    ("internal", "COPY internal/ /app/internal/"),
    ("data", "COPY data/ /app/data/"),
    ("config", "COPY config/ /app/config/"),
    ("docs", "COPY docs/ /app/docs/"),
    ("samples", "COPY samples/ /app/samples/"),
    ("scripts", "COPY scripts/ /app/scripts/"),
]

FOOTER = """
RUN mkdir -p /app/out /app/build \\
    && chmod +x /app/scripts/*.sh
"""


def build_dockerfile(env: Path) -> str:
    lines = [HEADER, RUN_BLOCK, '\n\nENV PATH="/usr/local/go/bin:${PATH}"\n\n']
    for name, copy_line in COPY_CANDIDATES:
        if name == "go.mod":
            if (env / "go.mod").is_file():
                lines.append(copy_line + "\n")
        elif (env / name).is_dir():
            lines.append(copy_line + "\n")
    lines.append(FOOTER)
    return "".join(lines)


def main() -> None:
    for task in TASKS:
        env = ROOT / task / "environment"
        df = env / "Dockerfile"
        if not env.is_dir():
            print(f"skip {task} (no environment/)")
            continue
        content = build_dockerfile(env)
        df.write_text(content, encoding="utf-8")
        dirs = [n for n, _ in COPY_CANDIDATES if n != "go.mod" and (env / n).is_dir()]
        print(f"fixed {task}: {', '.join(dirs)}")


if __name__ == "__main__":
    main()
