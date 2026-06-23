FROM rust:1.84-bookworm@sha256:738ae99a3d75623f41e6882566b4ef37e38a9840244a47efd4a0ca22e9628b88

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  python3=3.11.2-1+b1 \
  python3-venv=3.11.2-1+b1 \
  && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/verifier
RUN /opt/verifier/bin/pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5
ENV PATH=/opt/verifier/bin:${PATH}



# Rust bookworm image: full cargo path is /usr/local/cargo/bin/cargo when PATH is minimal.
ENV PATH="/usr/local/cargo/bin:${PATH}"

COPY Cargo.toml /app/Cargo.toml
COPY Cargo.lock /app/Cargo.lock
COPY config /app/config
COPY data /app/data
COPY src /app/src
COPY tests /app/tests

RUN cargo fetch --locked
RUN mkdir -p /app/output
# rustc/cargo binaries live under /usr/local/cargo/bin; keep that prefix ahead of distro stubs.
# Network fetches remain enabled post-build so solvers can adjust deps without brittle offline rejects.
