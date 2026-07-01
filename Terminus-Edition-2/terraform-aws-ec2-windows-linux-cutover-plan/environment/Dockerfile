FROM ghcr.io/laude-institute/t-bench/python-3-13:20250620

WORKDIR /app

ARG TERRAFORM_VERSION=1.9.8
ARG TERRAFORM_SHA256=186e0145f5e5f2eb97cbd785bc78f21bae4ef15119349f6ad4fa535b83b10df8
ARG AWS_PROVIDER_VERSION=5.83.1
ARG AWS_PROVIDER_SHA256=f698732a4391c3f4d7079b4aaa52389da2a460cac5eed438ed688f147d603689

COPY requirements.lock /tmp/requirements.lock
COPY terraform.tfrc /opt/terraform.tfrc

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates=20230311+deb12u1 \
    curl=7.88.1-10+deb12u14 \
    jq=1.6-2.1+deb12u1 \
    unzip=6.0-28 \
    && python3 -m pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && echo "${TERRAFORM_SHA256}  /tmp/terraform.zip" | sha256sum -c - \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && chmod 0755 /usr/local/bin/terraform \
    && rm -f /tmp/terraform.zip

RUN mkdir -p "/opt/terraform-providers/registry.terraform.io/hashicorp/aws/${AWS_PROVIDER_VERSION}/linux_amd64" \
    && curl -fsSLo /tmp/aws-provider.zip "https://releases.hashicorp.com/terraform-provider-aws/${AWS_PROVIDER_VERSION}/terraform-provider-aws_${AWS_PROVIDER_VERSION}_linux_amd64.zip" \
    && echo "${AWS_PROVIDER_SHA256}  /tmp/aws-provider.zip" | sha256sum -c - \
    && unzip -q /tmp/aws-provider.zip -d "/opt/terraform-providers/registry.terraform.io/hashicorp/aws/${AWS_PROVIDER_VERSION}/linux_amd64" \
    && chmod 0755 "/opt/terraform-providers/registry.terraform.io/hashicorp/aws/${AWS_PROVIDER_VERSION}/linux_amd64"/terraform-provider-aws* \
    && rm -f /tmp/aws-provider.zip

COPY scripts/ /app/environment/scripts/
COPY terraform/ /app/environment/terraform/

RUN test -d /app/environment/terraform/modules/ec2_linux_migration \
    && test -f /app/environment/terraform/modules/ec2_linux_migration/main.tf \
    && test -f /app/environment/terraform/modules/ec2_linux_migration/variables.tf \
    && test -f /app/environment/terraform/modules/ec2_linux_migration/outputs.tf

ENV TF_CLI_CONFIG_FILE="/opt/terraform.tfrc" \
    TF_IN_AUTOMATION="true" \
    AWS_EC2_METADATA_DISABLED="true" \
    AWS_ACCESS_KEY_ID="offline" \
    AWS_SECRET_ACCESS_KEY="offline" \
    AWS_DEFAULT_REGION="us-east-1"

RUN mkdir -p /app/output /app/output/run_logs
