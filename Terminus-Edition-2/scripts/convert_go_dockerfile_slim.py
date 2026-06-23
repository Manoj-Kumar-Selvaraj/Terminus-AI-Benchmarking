#!/usr/bin/env python3
"""Convert revision-queue Go Dockerfiles from golang:bookworm to debian-slim + go tarball."""
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

TEMPLATE = """FROM debian:bookworm-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb

WORKDIR /app

ENV GO_VERSION=1.22.12
ENV GO_SHA256=4fa4f869b0f7fc6bb1eb2660e74657fbf04cdd290b5aef905585c86051b34d43

RUN apt-get update \\
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
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/go/bin:${PATH}"

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


def main() -> None:
    for task in TASKS:
        p = ROOT / task / "environment" / "Dockerfile"
        if not p.is_file():
            print(f"skip {task} (no Dockerfile)")
            continue
        text = p.read_text(encoding="utf-8")
        if not text.startswith("FROM golang:"):
            print(f"skip {task} (already converted)")
            continue
        p.write_text(TEMPLATE, encoding="utf-8")
        print(f"converted {task}")


if __name__ == "__main__":
    main()
