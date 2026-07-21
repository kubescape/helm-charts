# GKE Autopilot allowlist tooling

Scripts for maintaining the GKE Autopilot **WorkloadAllowlists** that let the node-agent run on
Autopilot clusters. Background: [running the node-agent on GKE Autopilot](https://kubescape.io/docs/integrations/kubescape-integration-with-cloud-providers/running-armokubescape-node-agents-on-gke-autopilot-clusters/).

The approved allowlists live in ARMO's Google-managed (Gerrit) repo `gke-ap-allowlist/ARMO`. A copy of
the current approved allowlist for this chart is vendored under [`../../gke-allowlist/`](../../gke-allowlist/)
so CI can check the chart against it without network/auth.

## Why this matters

GKE Autopilot admission is **subset-based**: a pod is admitted only if its env vars, containers,
mounts and capabilities are a **subset** of the matched allowlist. So if a chart change adds a new
env var / mount / capability / container to the node-agent that the approved allowlist doesn't list,
**customers on Autopilot can no longer install** until a new allowlist is approved (Gerrit review +
gradual rollout). The release drift gate (below) catches that before release.

## Scripts

| Script | Purpose |
|--------|---------|
| `allowlist-drift.py` | Classify a chart render vs an allowlist as `no-op` / `digest-only` / `spec-drift`. Exit 2 on spec-drift (CI-gate friendly). |
| `check-drift.sh` | Wrapper script the release CI calls: renders the node-agent with all optional features on and runs `allowlist-drift.py`. |
| `build-allowlists.py` | (allowlist-repo side) Assemble final WorkloadAllowlist files from GKE-generated baselines + value overlays + image digests. |
| `refresh-digests.py` | (allowlist-repo side) Append newly-released node-agent image SHA-256 digests to an approved allowlist's mutable `containerImageDigests` field. |

## Run the drift check locally

```bash
# public kubescape chart
scripts/gke-allowlist/check-drift.sh charts/kubescape-operator \
  gke-allowlist/armo-kubescape-node-agent-1.40-v2.yaml
```
Exit 0 = covered; exit 2 = drift (the render needs something the allowlist lacks — the output names
each missing env/mount/container).

Use a **Helm ≥ 3.18** matching the pinned `version:` in `.github/workflows/pr-allowlist-drift.yaml`.
The check is only meaningful if it renders the chart the way users' Helm does, and old Helm can
differ enough to break the render outright: Helm ≤ 3.10 is built with Go < 1.18, where template
`and`/`or` evaluate every argument instead of short-circuiting, so a guard like
`and .X (gt (len .X) 0)` fails with `len of nil pointer`. Don't leave the workflow's `setup-helm`
on the default `version: latest` — without a token it can't resolve "latest" and silently installs
v3.9.0.

## When the drift gate fails on a release

1. The node-agent's privileged surface changed and needs a **new allowlist version**.
2. Create it in the `ARMO` allowlist repo (see `build-allowlists.py` / the process runbook), open a
   Gerrit change, and get it approved.
3. Update the vendored copy under `gke-allowlist/` to match, and bump the chart's
   `nodeAgent.gke.allowlist.name` default.
4. Re-run the release with the **`BYPASS_ALLOWLIST_DRIFT`** input set to `true` ("set as pass after
   you opened Gerrit to allowlist") while the new allowlist works through approval + rollout.

## Limitation

The check covers subset-matched fields (env names, containers, capabilities, mounts, hostPath
volumes, image repo). It does **not** see runtime-only fields such as the per-node-group
`node.kubernetes.io/instance-type` nodeSelector the autoscaler adds (that requires the
`autogke-node-affinity-selector-limitation` exemption) — validate those on a live Autopilot cluster.
