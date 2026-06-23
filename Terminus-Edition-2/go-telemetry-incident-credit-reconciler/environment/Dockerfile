FROM golang:1.22.12-bookworm@sha256:1f298b0c9fecdf504389a0329236f948cc04a566a2bb32337207cbaaa2f8177c

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
