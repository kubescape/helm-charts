#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=""
REQUEST_BODY=""
GENERATE_NAME=""
OWNER_JOB="${JOB_NAME:-}"

usage() {
  cat >&2 <<EOF
Usage: create-operator-command.sh [flags]
  -n, --namespace      Namespace to create the OperatorCommand objects in (required)
  -f, --request-body   Path to the request body JSON, {"commands": [...]} (required)
  -g, --generate-name  metadata.generateName prefix of the created objects (required)
      --owner-job      Job that owns the created objects (default: \$JOB_NAME)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)     NAMESPACE="$2";     shift 2;;
    -f|--request-body)  REQUEST_BODY="$2";  shift 2;;
    -g|--generate-name) GENERATE_NAME="$2"; shift 2;;
    --owner-job)        OWNER_JOB="$2";     shift 2;;
    -h|--help)          usage;;
    *) echo "unknown flag: $1" >&2; usage;;
  esac
done

[[ -n "$NAMESPACE"     ]] || { echo "--namespace required"     >&2; usage; }
[[ -n "$REQUEST_BODY"  ]] || { echo "--request-body required"  >&2; usage; }
[[ -n "$GENERATE_NAME" ]] || { echo "--generate-name required" >&2; usage; }

# The root filesystem is read-only; keep kubectl's discovery cache on the tmp volume.
export KUBECACHEDIR="${KUBECACHEDIR:-/tmp/kube-cache}"

COUNT="$(jq -er '.commands | length' "$REQUEST_BODY")" || { echo "$REQUEST_BODY has no commands array" >&2; exit 1; }
[[ "$COUNT" -gt 0 ]] || { echo "$REQUEST_BODY has no commands" >&2; exit 1; }

# Owning the objects by the Job lets Kubernetes garbage-collect them together with the
# Job history instead of leaving one OperatorCommand behind per run.
OWNER_REFS="[]"
if [[ -n "$OWNER_JOB" ]]; then
  JOB_UID="$(kubectl -n "$NAMESPACE" get job "$OWNER_JOB" -o jsonpath='{.metadata.uid}')"
  OWNER_REFS="$(jq -cn --arg name "$OWNER_JOB" --arg uid "$JOB_UID" \
    '[{apiVersion: "batch/v1", kind: "Job", name: $name, uid: $uid}]')"
fi

for ((i = 0; i < COUNT; i++)); do
  GUID="$(jq -r --argjson i "$i" '.commands[$i].jobTracking.jobID // empty' "$REQUEST_BODY")"
  [[ -n "$GUID" ]] || GUID="$(cat /proc/sys/kernel/random/uuid)"
  jq -c --argjson i "$i" --arg ns "$NAMESPACE" --arg prefix "$GENERATE_NAME" --arg guid "$GUID" --argjson owners "$OWNER_REFS" '{
    apiVersion: "kubescape.io/v1alpha1",
    kind: "OperatorCommand",
    metadata: {
      generateName: $prefix,
      namespace: $ns,
      labels: {"kubescape.io/app-name": "operator"},
      ownerReferences: $owners
    },
    spec: {
      guid: $guid,
      commandType: "OperatorAPI",
      body: (.commands[$i] | tojson | @base64)
    }
  }' "$REQUEST_BODY" | kubectl -n "$NAMESPACE" create -f -
done
