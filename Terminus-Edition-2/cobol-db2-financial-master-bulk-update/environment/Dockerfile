FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        diffutils \
        golang-1.19-go=1.19.8-2 \
        golang-1.19-src=1.19.8-2 \
        golang-go=2:1.19~1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY bin/ /app/bin/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY scripts/ /app/scripts/
COPY tools/ /app/tools/

RUN chmod +x /app/bin/run_finbulk.sh /app/bin/finbulk_op.sh /app/bin/db2_bridge_call.sh /app/scripts/reset_lab.sh \
    && mkdir -p /app/out /app/build \
    && go build -o /app/build/finbulk ./cmd/finbulk \
    && go build -o /app/build/db2bridge ./cmd/db2bridge \
    && go build -o /app/build/inspect-state ./cmd/inspect-state
