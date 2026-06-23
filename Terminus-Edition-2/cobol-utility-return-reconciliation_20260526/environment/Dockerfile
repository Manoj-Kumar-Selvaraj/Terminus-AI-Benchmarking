FROM --platform=linux/amd64 debian:bookworm-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    asciinema \
    ca-certificates \
    curl \
    gnucobol \
    make \
    python3 \
    python3-pip \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5


COPY src/ /app/src/
COPY copybooks/ /app/copybooks/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
