FROM debian:bookworm-slim@sha256:b29f74a267526ae6ea104eed6c46133b0ca70ce812525df8cd5817698f0a624a
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    gnucobol \
    make \
    openjdk-17-jdk \
    python3 \
    python3-pip \
    python3-venv \
    tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5


COPY src/ /app/src/
COPY java/ /app/java/
COPY rules/ /app/rules/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY copybooks/ /app/copybooks/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

ENV RULES_URL=http://localhost:8080

RUN mkdir -p /app/out /app/build \
    && javac -d /app/build /app/rules/RuleServer.java \
    && chmod +x /app/scripts/*.sh
