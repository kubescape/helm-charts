#!/usr/bin/env bash
# check-drift.sh — fail if a chart's node-agent render drifts from a vendored GKE
# Autopilot WorkloadAllowlist. Used by the release CI drift gate and runnable locally.
#
# Usage:
#   check-drift.sh <chart-dir> <allowlist-yaml> [--wrapper]
#
# --wrapper : the chart wraps the public kubescape-operator subchart, so values are
#             nested under the `kubescape-operator.` key.
#
# Checks the supported Autopilot profiles: proxy with the in-process scanner, and
# the SBOM sidecar without a proxy. The bundled allowlist cannot admit both at once;
# the chart rejects that combination. Exit 2 if either supported profile drifts.
set -euo pipefail

CHART="${1:?chart dir required}"
ALLOWLIST="${2:?allowlist yaml required}"
WRAPPER="${3:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

prefix=""
[ "$WRAPPER" = "--wrapper" ] && prefix="kubescape-operator."

helm dependency build "$CHART" >/dev/null

# Match the allowlist under test, including the chart's legacy API-token fallback.
# Testing a generic (non-Autopilot) render produces a false token-mount finding.
ALLOWLIST_NAME=$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["metadata"]["name"])' "$ALLOWLIST")
common=(
  --chart "$CHART" --allowlist "$ALLOWLIST"
  --set "${prefix}nodeAgent.gke.allowlist.enabled=true"
  --set "${prefix}nodeAgent.gke.allowlist.name=$ALLOWLIST_NAME"
  --set "${prefix}server=api.example.com"
  --set "${prefix}accessKey=00000000-0000-0000-0000-000000000000"
  --set "${prefix}capabilities.malwareDetection=enable"
  --set "${prefix}capabilities.nodeSbomGeneration=enable"
  --set "${prefix}configurations.otelUrl=http://otel-collector:4317"
  --set "${prefix}global.overrideRuntimePath=/run/containerd/containerd.sock"
  --set "${prefix}nodeAgent.config.skipKernelVersionCheck=true"
  --set "${prefix}nodeAgent.config.malwareScanAllFiles=true"
  --set "${prefix}nodeAgent.config.prometheusExporter=enable"
)
if [ -n "$WRAPPER" ]; then
  [ "$WRAPPER" = "--wrapper" ] || { echo "Unknown argument: $WRAPPER" >&2; exit 1; }
  common+=(--wrapper)
fi

status=0
for profile in proxy sbom-scanner; do
  echo "# Autopilot profile: $profile"
  if [ "$profile" = proxy ]; then
    settings=(--set "${prefix}nodeAgent.sbomScanner.enabled=false"
              --set "${prefix}global.httpsProxy=http://proxy:3128")
  else
    settings=(--set "${prefix}nodeAgent.sbomScanner.enabled=true"
              --set "${prefix}global.httpsProxy=")
  fi
  if python3 "$HERE/allowlist-drift.py" "${common[@]}" "${settings[@]}"; then
    :
  else
    rc=$?
    # A render/tool error must never be converted to an ack-able drift result.
    [ "$rc" -eq 2 ] || exit "$rc"
    status=2
  fi
done
exit "$status"
