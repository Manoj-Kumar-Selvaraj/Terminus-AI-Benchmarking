#!/usr/bin/env bash
set -Eeuo pipefail

# Standalone cumulative oracle for milestone 4.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

apply_patches() {
  for patch in "$@"; do
    patch -p0 -N -r - -d / < "${SCRIPT_DIR}/patches/${patch}"
  done
}

apply_patches Assertion.patch Policy.patch Replay.patch Rotation.patch

chmod 0555 /app/bin/brokerctl
export PERL5LIB=/app/lib
perl -c /app/bin/brokerctl >/dev/null
echo 'milestone 4 cumulative security repair applied'
