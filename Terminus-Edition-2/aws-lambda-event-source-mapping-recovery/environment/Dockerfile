# Dual-runtime image: Python runs the offline simulator/tests; Node.js runs the Lambda handler subprocess.
FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ROOT=/app \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        nodejs \
        python3 \
        python3-pip \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY config/ /app/config/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY handler/ /app/handler/
COPY ops/ /app/ops/
COPY observability/ /app/observability/
COPY runbooks/ /app/runbooks/
COPY scripts/ /app/scripts/
COPY src/ /app/src/
COPY tests_support/ /app/tests_support/

RUN chmod +x /app/scripts/*.py /app/scripts/*.sh && mkdir -p /logs/verifier /app/tmp
