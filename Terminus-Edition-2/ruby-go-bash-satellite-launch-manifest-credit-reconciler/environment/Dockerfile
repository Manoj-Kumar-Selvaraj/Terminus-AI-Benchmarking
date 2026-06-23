FROM ruby:3.3.5-slim@sha256:25a9df53c6f23406f6bc87426ad5bd74b6d99423a8c2ca630f2443dee2447f53

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates python3 python3-pip tmux \
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

COPY app/ /app/app/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh \
    && find /app/app -name '*.rb' -exec chmod +x {} +
