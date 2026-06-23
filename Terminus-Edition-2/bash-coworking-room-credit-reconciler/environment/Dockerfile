FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

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
