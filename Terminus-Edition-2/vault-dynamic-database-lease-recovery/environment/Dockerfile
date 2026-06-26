FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

COPY requirements.lock /tmp/requirements.lock

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
        golang-go=2:1.19~1 \
        golang-src=2:1.19~1 \
        golang-1.19-go=1.19.8-2 \
        golang-1.19-src=1.19.8-2 \
    && pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && mkdir -p /usr/local/go/bin \
    && ln -sf /usr/bin/go /usr/local/go/bin/go \
    && ln -sf /usr/bin/gofmt /usr/local/go/bin/gofmt \
    && rm -f /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/go/bin:/usr/bin:${PATH}" \
    CGO_ENABLED=0
WORKDIR /app

COPY task-tools/vault-db-runtime /opt/task-tools/vault-db-runtime
RUN chmod 0555 /opt/task-tools/vault-db-runtime \
    && sha256sum /opt/task-tools/vault-db-runtime > /opt/task-tools/vault-db-runtime.sha256

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY config/ /app/config/
COPY data/ /app/data/
COPY state/ /app/state/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/build /app/state /app/logs /var/lib/vault-db-runtime \
    && chmod +x /app/scripts/*.sh \
    && /opt/task-tools/vault-db-runtime reset \
    && go build -o /app/build/lease-agent ./cmd/lease-agent \
    && go build -o /app/build/payment-api ./cmd/payment-api
