FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS tools_build

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        golang-go=2:1.19~1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY tools/capability-lab/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-buildid=' -o /out/capability-lab ./main.go

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive \
    PERL5LIB=/app/lib

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        ca-certificates \
        patch \
        perl \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bin/ /app/bin/
COPY lib/ /app/lib/
COPY config/ /app/config/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY state/ /app/state/
COPY scripts/ /app/scripts/
COPY protected-baseline/ /opt/task-tools/baseline/
COPY tools/capability-lab/ /opt/task-tools/src/capability-lab/
COPY protected-manifest.sha256 /opt/task-tools/protected-manifest.sha256
COPY --from=tools_build /out/capability-lab /opt/task-tools/capability-lab

RUN chmod 0555 /opt/task-tools/capability-lab \
    && chmod 0555 /app/bin/brokerctl /app/scripts/*.sh \
    && mkdir -p /app/runtime/config /app/run /logs/verifier \
    && /opt/task-tools/capability-lab reset
