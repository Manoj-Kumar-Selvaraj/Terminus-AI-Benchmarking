FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY cmd/ /app/cmd/
COPY migration/ /app/migration/
COPY src/ /app/src/
COPY config/ /app/config/
COPY data/ /app/data/
COPY state/ /app/state/
COPY evidence/ /app/evidence/
COPY docs/ /app/docs/
COPY protected-manifest.json /app/protected-manifest.json
COPY task-tools/ /opt/task-tools/

RUN chmod 0555 /opt/task-tools/pg-repl-runtime \
    && chmod 0444 /opt/task-tools/runtime_lib.py /opt/task-tools/protected-hashes.json \
    && find /opt/task-tools/baseline-state -type f -exec chmod 0444 {} + \
    && mkdir -p /logs/verifier
