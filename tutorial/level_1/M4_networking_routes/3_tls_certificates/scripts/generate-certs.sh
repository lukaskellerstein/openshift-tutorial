#!/bin/bash
# generate-certs.sh
# Generates a self-signed CA and server certificate for TLS demo purposes.
# The server certificate is valid for *.apps-crc.testing (CRC wildcard domain).
#
# Usage: bash scripts/generate-certs.sh
#
# Output directory: certs/
#   ca.crt, ca.key       -- Certificate Authority
#   server.crt, server.key, server.csr -- Server certificate signed by the CA

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"
CERT_DIR="${LESSON_DIR}/certs"
DOMAIN="*.apps-crc.testing"
CA_SUBJECT="/CN=Tutorial Demo CA"
SERVER_SUBJECT="/CN=${DOMAIN}"
DAYS_VALID=365

echo "=== Generating self-signed certificates for TLS demo ==="
echo "Output directory: ${CERT_DIR}"
echo "Domain: ${DOMAIN}"
echo ""

# Create output directory
mkdir -p "${CERT_DIR}"

# Step 1: Generate CA private key
echo "[1/5] Generating CA private key..."
openssl genrsa -out "${CERT_DIR}/ca.key" 4096 2>/dev/null

# Step 2: Generate CA certificate
echo "[2/5] Generating CA certificate..."
openssl req -x509 -new -nodes \
  -key "${CERT_DIR}/ca.key" \
  -sha256 \
  -days ${DAYS_VALID} \
  -out "${CERT_DIR}/ca.crt" \
  -subj "${CA_SUBJECT}"

# Step 3: Generate server private key
echo "[3/5] Generating server private key..."
openssl genrsa -out "${CERT_DIR}/server.key" 4096 2>/dev/null

# Step 4: Generate server CSR (Certificate Signing Request)
echo "[4/5] Generating server CSR..."
openssl req -new \
  -key "${CERT_DIR}/server.key" \
  -out "${CERT_DIR}/server.csr" \
  -subj "${SERVER_SUBJECT}"

# Step 5: Sign the server certificate with the CA
echo "[5/5] Signing server certificate with CA..."
openssl x509 -req \
  -in "${CERT_DIR}/server.csr" \
  -CA "${CERT_DIR}/ca.crt" \
  -CAkey "${CERT_DIR}/ca.key" \
  -CAcreateserial \
  -out "${CERT_DIR}/server.crt" \
  -days ${DAYS_VALID} \
  -sha256 2>/dev/null

echo ""
echo "=== Certificates generated successfully ==="
echo ""
echo "Files created:"
echo "  ${CERT_DIR}/ca.crt          -- CA certificate"
echo "  ${CERT_DIR}/ca.key          -- CA private key"
echo "  ${CERT_DIR}/server.crt      -- Server certificate (signed by CA)"
echo "  ${CERT_DIR}/server.key      -- Server private key"
echo "  ${CERT_DIR}/server.csr      -- Server CSR (can be deleted)"
echo ""
echo "CA subject:     $(openssl x509 -noout -subject -in "${CERT_DIR}/ca.crt")"
echo "Server subject: $(openssl x509 -noout -subject -in "${CERT_DIR}/server.crt")"
echo "Server issuer:  $(openssl x509 -noout -issuer -in "${CERT_DIR}/server.crt")"
echo "Valid until:     $(openssl x509 -noout -enddate -in "${CERT_DIR}/server.crt")"
