FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY docs /app/docs
COPY evidence /app/evidence
COPY infra /app/infra
COPY tools /app/tools
RUN mkdir -p /app/out /app/state /logs/verifier \
    && chmod 0555 /app/tools/ec2sim.py \
    && sha256sum /app/tools/ec2sim.py > /opt/ec2sim.sha256
