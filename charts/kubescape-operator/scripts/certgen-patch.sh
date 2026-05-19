#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=""
SECRET_NAME=""
CA_NAME="ca"
RESOURCE_TYPE=""
RESOURCE_NAME=""
RETRIES="60"
RETRY_INTERVAL="5"

usage() {
  cat >&2 <<EOF
Usage: certgen-patch.sh [flags]
  -n, --namespace        Namespace of the secret (required)
  -s, --secret-name      Name of the secret holding the CA (required)
  -c, --ca-name          Key inside the secret holding the CA cert (default: ca)
  -t, --resource-type    Resource to patch: apiservice | vwc (required)
  -r, --resource-name    Name of the resource to patch (required)
      --retries          Max patch attempts (default: 60)
      --retry-interval   Seconds between attempts (default: 5)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)      NAMESPACE="$2";      shift 2;;
    -s|--secret-name)    SECRET_NAME="$2";    shift 2;;
    -c|--ca-name)        CA_NAME="$2";        shift 2;;
    -t|--resource-type)  RESOURCE_TYPE="$2";  shift 2;;
    -r|--resource-name)  RESOURCE_NAME="$2";  shift 2;;
    --retries)           RETRIES="$2";        shift 2;;
    --retry-interval)    RETRY_INTERVAL="$2"; shift 2;;
    -h|--help)           usage;;
    *) echo "unknown flag: $1" >&2; usage;;
  esac
done

[[ -n "$NAMESPACE"     ]] || { echo "--namespace required"     >&2; usage; }
[[ -n "$SECRET_NAME"   ]] || { echo "--secret-name required"   >&2; usage; }
[[ -n "$RESOURCE_TYPE" ]] || { echo "--resource-type required" >&2; usage; }
[[ -n "$RESOURCE_NAME" ]] || { echo "--resource-name required" >&2; usage; }

case "$RESOURCE_TYPE" in
  apiservice|vwc) ;;
  *) echo "--resource-type must be 'apiservice' or 'vwc', got '$RESOURCE_TYPE'" >&2; exit 2;;
esac

CA_BUNDLE="$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" -o json | jq -er --arg k "$CA_NAME" '.data[$k] // empty')"
[[ -n "$CA_BUNDLE" ]] || { echo "no '$CA_NAME' key in secret $NAMESPACE/$SECRET_NAME" >&2; exit 1; }

patch_once() {
  case "$RESOURCE_TYPE" in
    apiservice)
      kubectl patch apiservice "$RESOURCE_NAME" --type=merge \
        -p "{\"spec\":{\"caBundle\":\"$CA_BUNDLE\",\"insecureSkipTLSVerify\":false}}"
      ;;
    vwc)
      kubectl patch validatingwebhookconfiguration "$RESOURCE_NAME" --type=json \
        -p "[{\"op\":\"add\",\"path\":\"/webhooks/0/clientConfig/caBundle\",\"value\":\"$CA_BUNDLE\"}]"
      ;;
  esac
}

for i in $(seq 1 "$RETRIES"); do
  if patch_once; then
    exit 0
  fi
  echo "patch attempt $i/$RETRIES failed, retrying in ${RETRY_INTERVAL}s" >&2
  sleep "$RETRY_INTERVAL"
done

echo "patch failed after $RETRIES attempts" >&2
exit 1
