# Build stage uses Debian slim (not the Python canonical image) because this task
# ships a Java 17 service plus a Python pytest verifier. The runtime stage below
# is the canonical python:3.13-slim-bookworm image; this stage only compiles
# the billing JAR and seeds the offline Maven cache copied into /root/.m2.
FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d AS java_build

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        maven=3.8.7-1 \
        openjdk-17-jdk-headless=17.0.19+10-1~deb12u2 \
    && rm -rf /var/lib/apt/lists/*

COPY pom.xml /build/pom.xml
COPY src/ /build/src/
RUN mvn -q -DskipTests package

# Agents recompile after code fixes, so the runtime image keeps JDK + Maven offline.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        openjdk-17-jdk-headless=17.0.19+10-1~deb12u2 \
        maven=3.8.7-1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV MAVEN_OPTS="-Dmaven.repo.local=/root/.m2/repository"

WORKDIR /app

COPY --from=java_build /root/.m2 /root/.m2
COPY pom.xml /app/pom.xml
COPY config/ /app/config/
COPY deploy/ /app/deploy/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY scripts/ /app/scripts/
COPY src/ /app/src/

RUN mkdir -p /app/data /app/run /app/target /app/build \
    && cd /app \
    && mvn -o -q -DskipTests package \
    && cp /app/target/billing-service-1.0.0.jar /app/build/billing-service.jar \
    && chmod +x /app/scripts/*.sh
