FROM python:3.13-slim-bookworm@sha256:3670a55aa5f1444dd6c6df1018cf2dbcea8d6b5872815a4e324375ed7cbea89f

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*


RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY src/ /app/src/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build && chmod +x /app/scripts/*.sh
