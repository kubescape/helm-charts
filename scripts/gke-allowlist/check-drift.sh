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
# Renders the node-agent with the FULL set of optional features enabled (server/API_URL,
# proxy, custom runtime, kernel-check skip, full malware scan, ClamAV, SBOM scanner, OTEL)
# so the check exercises the maximal privileged surface a customer could produce, then
# verifies it is a subset of the approved allowlist. Exit 2 on drift.
set -euo pipefail

CHART="${1:?chart dir required}"
ALLOWLIST="${2:?allowlist yaml required}"
WRAPPER="${3:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

prefix=""
[ "$WRAPPER" = "--wrapper" ] && prefix="kubescape-operator."

helm dependency build "$CHART" >/dev/null

exec python3 "$HERE/allowlist-drift.py" \
  --chart "$CHART" --allowlist "$ALLOWLIST" ${WRAPPER:+$WRAPPER} \
  --set "${prefix}server=api.example.com" \
  --set "${prefix}accessKey=00000000-0000-0000-0000-000000000000" \
  --set "${prefix}capabilities.malwareDetection=enable" \
  --set "${prefix}capabilities.nodeSbomGeneration=enable" \
  --set "${prefix}nodeAgent.sbomScanner.enabled=true" \
  --set "${prefix}configurations.otelUrl=http://otel-collector:4317" \
  --set "${prefix}global.httpsProxy=http://proxy:3128" \
  --set "${prefix}global.overrideRuntimePath=/run/containerd/containerd.sock" \
  --set "${prefix}nodeAgent.config.skipKernelVersionCheck=true" \
  --set "${prefix}nodeAgent.config.malwareScanAllFiles=true"
