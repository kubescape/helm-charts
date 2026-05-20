#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=""
SECRET_NAME=""
HOSTS=""
OUT_DIR=""
CA_NAME="ca"
CERT_NAME="cert"
KEY_NAME="key"
DAYS="36500"

usage() {
  cat >&2 <<EOF
Usage: certgen-create.sh [flags]
  -n, --namespace      Namespace for the secret (required)
  -s, --secret-name    Name of the secret to read/create (required)
  -H, --host           Comma-separated DNS SANs for the leaf cert (required)
  -o, --out-dir        Directory to write the leaf cert/key into (required)
      --ca-name        Key in the secret for the CA cert (default: ca)
      --cert-name      Key in the secret for the leaf cert (default: cert)
      --key-name       Key in the secret for the leaf key (default: key)
      --days           Validity in days (default: 36500 ~= 100y)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)   NAMESPACE="$2";   shift 2;;
    -s|--secret-name) SECRET_NAME="$2"; shift 2;;
    -H|--host)        HOSTS="$2";       shift 2;;
    -o|--out-dir)     OUT_DIR="$2";     shift 2;;
    --ca-name)        CA_NAME="$2";     shift 2;;
    --cert-name)      CERT_NAME="$2";   shift 2;;
    --key-name)       KEY_NAME="$2";    shift 2;;
    --days)           DAYS="$2";        shift 2;;
    -h|--help)        usage;;
    *) echo "unknown flag: $1" >&2; usage;;
  esac
done

[[ -n "$NAMESPACE"   ]] || { echo "--namespace required"   >&2; usage; }
[[ -n "$SECRET_NAME" ]] || { echo "--secret-name required" >&2; usage; }
[[ -n "$HOSTS"       ]] || { echo "--host required"        >&2; usage; }
[[ -n "$OUT_DIR"     ]] || { echo "--out-dir required"     >&2; usage; }

mkdir -p "$OUT_DIR"

# --- path 1: secret already exists -> just materialize cert / key ---
if SECRET_JSON="$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" -o json 2>/dev/null)"; then
  echo "secret $NAMESPACE/$SECRET_NAME exists, reusing"
  echo "$SECRET_JSON" | jq -er --arg k "$CERT_NAME" '.data[$k] // empty' | base64 -d > "$OUT_DIR/$CERT_NAME"
  echo "$SECRET_JSON" | jq -er --arg k "$KEY_NAME"  '.data[$k] // empty' | base64 -d > "$OUT_DIR/$KEY_NAME"
  [[ -s "$OUT_DIR/$CERT_NAME" && -s "$OUT_DIR/$KEY_NAME" ]] || { echo "secret missing $CERT_NAME/$KEY_NAME" >&2; exit 1; }
  exit 0
fi

# --- path 2: generate CA + leaf, save locally and to a new secret ---
echo "secret $NAMESPACE/$SECRET_NAME not found, generating"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Build SANs from the comma-separated host list (DNS only).
SAN=""; i=0
IFS=',' read -ra HOST_ARR <<< "$HOSTS"
for h in "${HOST_ARR[@]}"; do
  i=$((i+1))
  SAN+="DNS.${i} = ${h}"$'\n'
done

cat > "$TMP/leaf.cnf" <<EOF
[req]
distinguished_name = dn
req_extensions     = v3
prompt             = no
[dn]
CN = ${HOST_ARR[0]}
[v3]
subjectAltName = @san
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
[san]
${SAN}
EOF

# CA
openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/ca.key"
openssl req -x509 -new -key "$TMP/ca.key" -days "$DAYS" -subj "/O=certgen-ca" -out "$TMP/ca.crt"

# Leaf
openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/tls.key"
openssl req -new -key "$TMP/tls.key" -config "$TMP/leaf.cnf" -out "$TMP/tls.csr"
openssl x509 -req -in "$TMP/tls.csr" -CA "$TMP/ca.crt" -CAkey "$TMP/ca.key" -CAcreateserial \
  -days "$DAYS" -extensions v3 -extfile "$TMP/leaf.cnf" -out "$TMP/tls.crt"

# Local copy for the pod (filenames mirror the secret keys).
cp "$TMP/tls.crt" "$OUT_DIR/$CERT_NAME"
cp "$TMP/tls.key" "$OUT_DIR/$KEY_NAME"

# Persist to a new secret so subsequent pod restarts and the patch step can reuse it.
kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  --from-file="${CA_NAME}=$TMP/ca.crt" \
  --from-file="${CERT_NAME}=$TMP/tls.crt" \
  --from-file="${KEY_NAME}=$TMP/tls.key"
