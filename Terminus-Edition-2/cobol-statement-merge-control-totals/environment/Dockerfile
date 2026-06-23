# No canonical GnuCOBOL image is available; digest-pinned Debian supplies GnuCOBOL
# and the required Terminal-Bench session and Python test tooling.
# Single-stage build is intentional: agents recompile COBOL at runtime (static-check carve-out).
FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        bash \
        ca-certificates \
        gnucobol3=3.1.2-5+b1 \
        make \
        python3 \
        python3-pip \
        tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app

COPY src/ /app/src/
COPY copybooks/ /app/copybooks/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
