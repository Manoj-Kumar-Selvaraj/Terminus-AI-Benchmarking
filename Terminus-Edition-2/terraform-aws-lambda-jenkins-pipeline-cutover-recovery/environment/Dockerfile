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
    && /usr/local/bin/python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && mkdir -p /usr/local/go/bin \
    && ln -sf /usr/bin/go /usr/local/go/bin/go \
    && ln -sf /usr/bin/gofmt /usr/local/go/bin/gofmt \
    && rm -f /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/verifier/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:${PATH}" \
    CGO_ENABLED=0

WORKDIR /trusted-src
COPY tools/runtime/main.go ./main.go
RUN /usr/local/go/bin/go build -trimpath -ldflags="-s -w" -o /opt/task-tools/lambda-pipeline-runtime ./main.go \
    && chmod 0555 /opt/task-tools/lambda-pipeline-runtime \
    && sha256sum /opt/task-tools/lambda-pipeline-runtime > /opt/task-tools/lambda-pipeline-runtime.sha256 \
    && rm -rf /trusted-src

WORKDIR /app

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY infra/ /app/infra/
COPY config/ /app/config/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/bin /app/state /app/dist /logs/verifier /var/lib/lambda-pipeline-runtime \
    && chmod +x /app/scripts/*.sh \
    && /usr/local/go/bin/go build -o /app/bin/pipelinectl /app/cmd/pipelinectl \
    && /opt/task-tools/lambda-pipeline-runtime reset >/dev/null
