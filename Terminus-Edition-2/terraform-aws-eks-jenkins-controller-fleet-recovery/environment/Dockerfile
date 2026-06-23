FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
# Installs the hash-pinned pytest runner and its explicit --no-deps dependencies.
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY docs /app/docs
COPY evidence /app/evidence
COPY fixtures /app/fixtures
COPY scripts /app/scripts
COPY terraform /app/terraform
RUN chmod +x /app/scripts/*.py
