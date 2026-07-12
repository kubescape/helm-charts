# GKE Autopilot Allowlist Tooling & Release Drift Gate

## Overview

Running the `node-agent` on **GKE Autopilot** requires a Google-approved `WorkloadAllowlist` — Autopilot
blocks privileged workloads unless a matching allowlist is installed (via an `AllowlistSynchronizer`).
ARMO maintains those allowlists in a Google-managed (Gerrit) repository; this chart's node-agent is
matched against `armo-kubescape-node-agent-<chart-minor>`.

This feature adds tooling to keep the chart and the approved allowlist in sync, and a **release-time
gate** that prevents shipping a chart the approved allowlist can no longer admit.

## Why a gate is needed

GKE Autopilot admission is **subset-based**: a pod is admitted only if its environment variables,
containers, mounts, and Linux capabilities are a **subset** of the matched allowlist. If a chart change
adds something new to the node-agent (a new env var, mount, capability, or sidecar) that the approved
allowlist does not list, **customers on Autopilot can no longer install the chart** until a new
allowlist is approved — which involves Google review and a gradual rollout. The gate catches this at
release time instead of in the field.

## Components

- **`scripts/gke-allowlist/allowlist-drift.py`** — renders the node-agent and classifies it against an
  allowlist as `no-op`, `digest-only`, or `spec-drift` (exit code 2 on spec-drift).
- **`scripts/gke-allowlist/check-drift.sh`** — the wrapper the release workflow calls. It renders the
  node-agent with the full set of optional features enabled (backend server/`API_URL`, HTTP proxy,
  custom runtime path, kernel-check skip, full malware scan, ClamAV, SBOM scanner, OTEL) so the check
  exercises the maximal privileged surface, then verifies it is a subset of the allowlist.
- **`scripts/gke-allowlist/build-allowlists.py`, `refresh-digests.py`** — allowlist-repo-side helpers
  (assemble allowlist files; append new node-agent image digests to the mutable `containerImageDigests`
  field). Documented in `scripts/gke-allowlist/README.md`.
- **`gke-allowlist/armo-kubescape-node-agent-1.40-v2.yaml`** — a vendored copy of the currently approved
  allowlist, so the gate runs with no network or auth.

## Release behavior

The `03-helm-release.yaml` workflow runs an `allowlist-drift-check` job before publishing:

- **No drift** → job passes, release proceeds.
- **Drift detected** → job **fails** with the specific missing fields, blocking the release.
- **Intentional drift** (you are shipping a change that needs a new allowlist): open the Gerrit
  allowlist update first, then re-run the release with the **`BYPASS_ALLOWLIST_DRIFT: true`** input.
  The gate then passes with a warning ("set as pass after you opened Gerrit to allowlist").

When drift is intentional, also update the vendored `gke-allowlist/` copy and the chart's
`nodeAgent.gke.allowlist.name` default to the new allowlist once it is approved.

## Run locally

```bash
scripts/gke-allowlist/check-drift.sh charts/kubescape-operator \
  gke-allowlist/armo-kubescape-node-agent-1.40-v2.yaml
```

## Limitation

The check covers subset-matched fields (env names, containers, capabilities, mounts, hostPath volumes,
image repo). It does not see runtime-only fields such as the per-node-group
`node.kubernetes.io/instance-type` nodeSelector the autoscaler adds (which needs the
`autogke-node-affinity-selector-limitation` exemption) — validate those on a live Autopilot cluster.
