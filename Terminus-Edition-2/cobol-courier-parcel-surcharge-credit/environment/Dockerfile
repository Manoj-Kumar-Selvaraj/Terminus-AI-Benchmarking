FROM debian:bookworm-slim@sha256:b29f74a267526ae6ea104eed6c46133b0ca70ce812525df8cd5817698f0a624a

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema bash ca-certificates gnucobol make python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY src/ /app/src/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh

WORKDIR /app
