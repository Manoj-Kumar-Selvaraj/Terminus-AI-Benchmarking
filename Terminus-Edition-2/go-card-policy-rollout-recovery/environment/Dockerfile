# The canonical final image is Python slim; Go is copied from a digest-pinned
# builder because this Go task needs the toolchain and no canonical Go image is
# available in the accepted base-image list.
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS go_runtime

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

COPY --from=go_runtime /usr/local/go /usr/local/go

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/bin /app/out \
    && chmod +x /app/scripts/*.sh \
    && /app/scripts/build.sh
