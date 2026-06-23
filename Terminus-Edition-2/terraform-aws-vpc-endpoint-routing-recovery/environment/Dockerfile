FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5

WORKDIR /app
COPY modules /app/modules
COPY stacks /app/stacks
COPY docs /app/docs
COPY evidence /app/evidence
COPY fixtures /app/fixtures
COPY scripts /app/scripts

RUN mkdir -p /logs/verifier /tmp/network-inspector
