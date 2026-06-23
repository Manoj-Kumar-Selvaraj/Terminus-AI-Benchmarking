FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && pip3 install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        PyYAML==6.0.2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY manifests/ /app/manifests/
COPY sim/ /app/sim/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out \
    && chmod +x /app/scripts/*.sh
