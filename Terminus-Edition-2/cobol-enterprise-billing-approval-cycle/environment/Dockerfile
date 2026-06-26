# Canonical Python base for pytest verifiers; GnuCOBOL comes from Debian apt.
# Single-stage build is intentional: agents recompile COBOL at runtime (static-check carve-out).
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive \
    COB_LS_FIXED=Y

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        bash \
        ca-certificates \
        gnucobol \
        make \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY src/ /app/src/
COPY copybooks/ /app/copybooks/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build /logs/verifier \
    && chmod +x /app/scripts/*.sh
