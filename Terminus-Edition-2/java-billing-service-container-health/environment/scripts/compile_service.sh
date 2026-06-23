#!/usr/bin/env bash
set -euo pipefail
cd /app
mvn -o -q -DskipTests package
cp /app/target/billing-service-1.0.0.jar /app/build/billing-service.jar
