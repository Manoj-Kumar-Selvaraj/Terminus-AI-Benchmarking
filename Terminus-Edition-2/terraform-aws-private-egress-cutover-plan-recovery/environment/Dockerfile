FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ARG TERRAFORM_VERSION=1.9.8
ARG TERRAFORM_SHA256=186e0145f5e5f2eb97cbd785bc78f21bae4ef15119349f6ad4fa535b83b10df8

COPY requirements.lock /tmp/requirements.lock

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates=20230311+deb12u1 \
       curl \
       unzip=6.0-28 \
       tmux=3.3a-3 \
       asciinema=2.2.0-1 \
    && /usr/local/bin/python3 -m pip install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && /usr/local/bin/python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -f /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && echo "${TERRAFORM_SHA256}  /tmp/terraform.zip" | sha256sum -c - \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && rm -f /tmp/terraform.zip \
    && terraform version

COPY provider-seed/ /tmp/tf-mirror-seed/
COPY terraformrc /opt/terraformrc

RUN mkdir -p /opt/tf-provider-mirror \
    && cd /tmp/tf-mirror-seed \
    && terraform providers mirror /opt/tf-provider-mirror \
    && rm -rf /tmp/tf-mirror-seed

ENV PATH="/opt/verifier/bin:/usr/local/bin:/usr/bin:${PATH}" \
    TF_CLI_CONFIG_FILE="/opt/terraformrc" \
    AWS_ACCESS_KEY_ID="test" \
    AWS_SECRET_ACCESS_KEY="test" \
    AWS_EC2_METADATA_DISABLED="true" \
    TF_INPUT="0" \
    TF_IN_AUTOMATION="1"

WORKDIR /app
COPY modules/ /app/modules/
COPY fixtures/ /app/fixtures/
COPY evidence/ /app/evidence/
COPY docs/ /app/docs/
RUN test -f /app/docs/output_contract.md \
    && test -f /app/docs/module_contract.md \
    && test -f /app/docs/egress_contract.md
RUN mkdir -p /logs/verifier /tmp/tf-runs
