FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS go_runtime

WORKDIR /src
COPY simulator/ /src/
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/jenkins_cluster_sim .

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

COPY --from=go_runtime /usr/local/go /usr/local/go
COPY --from=go_runtime /out/jenkins_cluster_sim /app/scripts/jenkins_cluster_sim
ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux=3.3a-3 asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY scripts /app/scripts
COPY recovery /app/recovery
COPY cluster /app/cluster
COPY config /app/config
COPY docs /app/docs
COPY evidence /app/evidence
COPY backups /app/backups
COPY jenkins_home /app/jenkins_home
RUN chmod +x /app/scripts/*
