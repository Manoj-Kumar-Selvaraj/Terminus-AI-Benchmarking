FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS guard_builder

WORKDIR /src
COPY scripts/plan_guard.go /src/plan_guard.go
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/plan_guard /src/plan_guard.go

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY docs /app/docs
COPY evidence /app/evidence
COPY fixtures /app/fixtures
COPY scripts /app/scripts
COPY terraform /app/terraform
COPY --from=guard_builder /out/plan_guard /app/scripts/plan_guard
RUN chmod +x /app/scripts/plan_guard
