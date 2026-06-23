# The approved Python runtime does not include Go. This digest-pinned stage is
# used only as a portable source for /usr/local/go; the final task image remains
# the canonical Python 3.13 slim runtime and does not inherit the Go image OS.
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS go_runtime

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

COPY --from=go_runtime /usr/local/go /usr/local/go

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --break-system-packages --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

ENV PATH="/usr/local/go/bin:${PATH}"

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
