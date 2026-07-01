FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS go_builder

WORKDIR /trusted-src
COPY tools/runtime/main.go ./main.go
RUN go build -trimpath -ldflags="-s -w" -o /opt/task-tools/lambda-pipeline-runtime ./main.go \
    && chmod 0555 /opt/task-tools/lambda-pipeline-runtime \
    && sha256sum /opt/task-tools/lambda-pipeline-runtime > /opt/task-tools/lambda-pipeline-runtime.sha256

FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

COPY requirements.lock /tmp/requirements.lock

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates=20230311+deb12u1 \
       tmux=3.3a-3 \
       asciinema=2.2.0-1 \
       python3=3.11.2-1+b1 \
       python3-pip=23.0.1+dfsg-1 \
       python3-venv=3.11.2-1+b1 \
    && /usr/bin/python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go_builder /usr/local/go /usr/local/go
COPY --from=go_builder /opt/task-tools/lambda-pipeline-runtime /opt/task-tools/lambda-pipeline-runtime
COPY --from=go_builder /opt/task-tools/lambda-pipeline-runtime.sha256 /opt/task-tools/lambda-pipeline-runtime.sha256

ENV PATH="/opt/verifier/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:${PATH}" \
    CGO_ENABLED=0

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
    && go build -o /app/bin/pipelinectl /app/cmd/pipelinectl \
    && /opt/task-tools/lambda-pipeline-runtime reset >/dev/null
