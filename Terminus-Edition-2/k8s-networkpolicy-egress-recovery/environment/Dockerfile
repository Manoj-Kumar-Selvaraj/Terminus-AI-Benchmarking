FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        bash \
        ca-certificates \
        coreutils \
        findutils \
        gawk \
        grep \
        sed \
        tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY k8s/ /app/k8s/
COPY scripts/ /app/scripts/
RUN mkdir -p /app/out /logs/verifier
