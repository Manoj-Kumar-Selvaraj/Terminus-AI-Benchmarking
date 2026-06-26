#!/usr/bin/env bash
set -Eeuo pipefail
export PERL5LIB=/app/lib
for f in /app/bin/brokerctl /app/lib/Broker/*.pm; do perl -c "$f" >/dev/null; done
