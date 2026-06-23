#!/usr/bin/env bash
docker run --rm debian:bookworm-slim@sha256:b29f74a267526ae6ea104eed6c46133b0ca70ce812525df8cd5817698f0a624a bash -lc '
apt-get update -qq
for pkg in gnucobol make bash python3 python3-pip tmux asciinema ca-certificates; do
  echo "=== $pkg ==="
  apt-cache policy "$pkg" | grep Candidate
done
'
