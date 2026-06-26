FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates=20230311+deb12u1 \
       openjdk-17-jdk-headless \
       tmux=3.3a-3 \
    && pip3 install --no-cache-dir pytest==8.4.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/ /app/src/
COPY bin/ /app/bin/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY samples/ /app/samples/
RUN chmod +x /app/bin/signerctl
ENV PATH="/app/bin:${PATH}"
