FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS go_runtime

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive

COPY --from=go_runtime /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        diffutils \
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

RUN chmod +x /app/bin/run_finbulk.sh /app/scripts/reset_lab.sh /app/tools/*.py \
    && mkdir -p /app/out /app/build \
    && go build -o /app/build/finbulk /app/cmd/finbulk
