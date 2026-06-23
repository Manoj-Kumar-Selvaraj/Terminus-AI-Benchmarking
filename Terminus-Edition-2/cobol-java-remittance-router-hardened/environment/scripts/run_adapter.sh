#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
javac -d /app/build /app/java/RemittanceAdapter.java
java -cp /app/build RemittanceAdapter