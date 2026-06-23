FROM debian:bookworm-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb AS java_build

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        maven=3.8.7-1 \
        openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

COPY pom.xml /build/pom.xml
COPY src/ /build/src/
RUN mvn -q -DskipTests package

FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177

COPY --from=java_build /usr/lib/jvm/java-17-openjdk-amd64 /usr/lib/jvm/java-17-openjdk-amd64

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        maven=3.8.7-1 \
        openjdk-17-jdk-headless \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && pip3 install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /app

COPY --from=java_build /build/target/billing-service-1.0.0.jar /app/build/billing-service.jar
COPY config/ /app/config/
COPY deploy/ /app/deploy/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY scripts/ /app/scripts/
COPY src/ /app/src/
COPY pom.xml /app/pom.xml

RUN mkdir -p /app/data /app/run /app/target \
    && chmod +x /app/scripts/*.sh
