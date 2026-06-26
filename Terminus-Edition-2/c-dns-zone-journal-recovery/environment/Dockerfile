FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       bash \
       build-essential \
       ca-certificates \
       python3 \
       python3-pip \
       python3-venv \
       tmux=3.3a-3 \
       asciinema=2.2.0-1 \
    && python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/ /app/src/
COPY bin/ /app/bin/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY samples/ /app/samples/
RUN chmod +x /app/bin/zonectl
ENV PATH="/opt/verifier/bin:/app/bin:${PATH}"
