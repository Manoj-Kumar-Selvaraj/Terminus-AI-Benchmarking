FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gawk tmux asciinema \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY src/ /app/src/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/
COPY evidence/ /app/evidence/
COPY state/ /app/state/
COPY spool/ /app/spool/

RUN mkdir -p /app/out /app/build /app/state /app/spool/downlink_segments && chmod +x /app/scripts/*.sh
