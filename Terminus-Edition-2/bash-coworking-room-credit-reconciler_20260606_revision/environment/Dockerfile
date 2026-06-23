FROM debian:bookworm-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash=5.2.15-2+b13 \
    ca-certificates=20230311+deb12u1 \
    python3=3.11.2-1+b1 \
    python3-pytest=7.2.1-2 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY scripts/ /app/scripts/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY lib/ /app/lib/
COPY fixtures/ /app/fixtures/
RUN mkdir -p /app/out && chmod +x /app/scripts/*.sh
