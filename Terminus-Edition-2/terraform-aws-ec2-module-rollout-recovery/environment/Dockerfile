FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS go_builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends golang-go \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY go.mod /build/go.mod
COPY cmd/runner /build/cmd/runner
RUN go build -o /out/ec2sim ./cmd/runner \
    && cp -a /usr/lib/go-1.19 /out/go \
    && cp -a /usr/share/go-1.19 /out/go-share

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY --from=go_builder /out/go /usr/lib/go-1.19
COPY --from=go_builder /out/go-share /usr/share/go-1.19
COPY --from=go_builder /out/ec2sim /app/tools/ec2sim
RUN ln -s /usr/lib/go-1.19/bin/go /usr/local/bin/go \
	&& ln -s /usr/lib/go-1.19/bin/gofmt /usr/local/bin/gofmt \
    && chmod 0555 /app/tools/ec2sim
COPY docs /app/docs
COPY evidence /app/evidence
COPY go.mod /app/go.mod
COPY cmd/ec2sim /app/cmd/ec2sim
COPY cmd/runner /app/cmd/runner
COPY infra /app/infra
RUN mkdir -p /app/out /app/state /logs/verifier \
    && sha256sum /app/tools/ec2sim /app/infra/modules/ec2/module.go > /opt/ec2sim.sha256
