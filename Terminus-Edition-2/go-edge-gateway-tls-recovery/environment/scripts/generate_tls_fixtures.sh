#!/usr/bin/env bash
set -euo pipefail

CERT_ROOT="${1:-/app/certs}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$CERT_ROOT"/{ca,client,server,trust}

sign_cert() {
  local csr="$1"
  local issuer_cert="$2"
  local issuer_key="$3"
  local out="$4"
  openssl x509 -req -in "$csr" -CA "$issuer_cert" -CAkey "$issuer_key" \
    -CAcreateserial -days 3650 -sha256 -copy_extensions copy -out "$out"
}

openssl ecparam -name prime256v1 -genkey -noout -out "$WORK/root.key"

openssl req -new -x509 -key "$WORK/root.key" -days 3650 -sha256 \
  -subj "/O=Example Edge Platform/CN=Edge Platform Offline Root" \
  -out "$CERT_ROOT/ca/offline-root.pem"

for spec in "2025:retiring-issuer" "2026:replacement-issuer"; do
  year="${spec%%:*}"
  name="${spec##*:}"
  openssl ecparam -name prime256v1 -genkey -noout -out "$WORK/${name}.key"
  openssl req -new -key "$WORK/${name}.key" -sha256 \
    -subj "/O=Example Edge Platform/CN=Edge Issuing CA ${year}" \
    -out "$WORK/${name}.csr"
  sign_cert "$WORK/${name}.csr" "$CERT_ROOT/ca/offline-root.pem" "$WORK/root.key" \
    "$CERT_ROOT/ca/${name}.pem"
done

cp "$CERT_ROOT/ca/replacement-issuer.pem" "$CERT_ROOT/trust/current-issuer.pem"
cat "$CERT_ROOT/ca/retiring-issuer.pem" "$CERT_ROOT/ca/replacement-issuer.pem" \
  > "$CERT_ROOT/trust/rotation-bundle.pem"

for client in "v1:edge-gateway-v1" "v2:edge-gateway-v2"; do
  tag="${client%%:*}"
  cn="${client##*:}"
  openssl ecparam -name prime256v1 -genkey -noout -out "$CERT_ROOT/client/client-${tag}.key"
  openssl req -new -key "$CERT_ROOT/client/client-${tag}.key" -sha256 \
    -subj "/O=Example Edge Platform/CN=${cn}" \
    -out "$WORK/client-${tag}.csr"
  sign_cert "$WORK/client-${tag}.csr" "$CERT_ROOT/ca/replacement-issuer.pem" \
    "$WORK/replacement-issuer.key" "$CERT_ROOT/client/client-${tag}.pem"
done

issue_server() {
  local name="$1"
  local issuer_pem="$2"
  local issuer_key="$3"
  local san_ext="$4"
  openssl ecparam -name prime256v1 -genkey -noout -out "$CERT_ROOT/server/${name}.key"
  openssl req -new -key "$CERT_ROOT/server/${name}.key" -sha256 \
    -subj "/O=Example Edge Platform/CN=ledger.service.internal" \
    -addext "subjectAltName=${san_ext}" \
    -out "$WORK/${name}.csr"
  sign_cert "$WORK/${name}.csr" "$issuer_pem" "$issuer_key" \
    "$CERT_ROOT/server/${name}.pem"
}

issue_server "replacement-dns" "$CERT_ROOT/ca/replacement-issuer.pem" \
  "$WORK/replacement-issuer.key" "DNS:ledger.service.internal"
issue_server "replacement-ip" "$CERT_ROOT/ca/replacement-issuer.pem" \
  "$WORK/replacement-issuer.key" "IP:127.0.0.1"
issue_server "retiring-dns" "$CERT_ROOT/ca/retiring-issuer.pem" \
  "$WORK/retiring-issuer.key" "DNS:ledger.service.internal"

chmod 600 "$CERT_ROOT"/client/*.key "$CERT_ROOT"/server/*.key
