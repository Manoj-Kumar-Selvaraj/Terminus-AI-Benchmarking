FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ROOT=/app \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        golang-go=2:1.19~1 \
        nodejs=18.20.4+dfsg-1~deb12u2 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY config/ /app/config/
COPY control_plane/ /app/control_plane/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY handler/ /app/handler/
COPY ops/ /app/ops/
COPY observability/ /app/observability/
COPY runbooks/ /app/runbooks/
COPY scripts/ /app/scripts/
COPY simulator/ /app/simulator/
COPY tests_support/ /app/tests_support/

RUN cd /app/simulator \
    && go build -trimpath -o /app/scripts/run_simulation . \
    && chmod +x /app/scripts/run_simulation /app/scripts/run_simulation.py /app/scripts/run_simulation.sh \
    && mkdir -p /app/tmp
