# GKE Autopilot: automatic AllowlistSynchronizer

## Overview

To run the node-agent on **GKE Autopilot**, two things must be true:

1. The node-agent pod carries the `cloud.google.com/matching-allowlist` label naming its approved
   `WorkloadAllowlist`.
2. That `WorkloadAllowlist` is installed in the cluster — which GKE does via an `AllowlistSynchronizer`
   that pulls the allowlist from Google's managed repo.

Previously the chart did (1) but not (2): enabling `nodeAgent.gke.allowlist.enabled` only added the
label, and operators had to create the `AllowlistSynchronizer` separately. This feature makes the chart
also install the synchronizer, so enabling the allowlist is a single step.

## Behavior

When `nodeAgent.gke.allowlist.enabled=true`, the chart now renders an `AllowlistSynchronizer`
(`templates/node-agent/allowlistsynchronizer.yaml`) alongside the label:

- **Path** — derived from `nodeAgent.gke.allowlist.name` as `ARMO/<name-without-version-suffix>/*`
  (e.g. `armo-private-node-agent-1.40-v2` → `ARMO/armo-private-node-agent/*`). Override with
  `nodeAgent.gke.allowlist.path` if needed.
- **Name** — release-scoped (`<fullname>-gke-allowlist`), so it does not collide with an
  `AllowlistSynchronizer` an operator may already have created manually.
- **Cluster-scoped** — like the `WorkloadAllowlist` objects it manages.

When `nodeAgent.gke.allowlist.enabled=false` (the default), nothing is rendered — behavior is unchanged.

## Does not block `helm install`

The synchronizer only creates a synchronizer object; the actual `WorkloadAllowlist` install is
reconciled asynchronously by the GKE controller. If the target allowlist is **already present** in the
cluster (installed manually or by another synchronizer), the controller reconciles it in the
background — it does **not** fail `helm install`/`upgrade`.

## Values

| Value | Default | Purpose |
|-------|---------|---------|
| `nodeAgent.gke.allowlist.enabled` | `false` | Label the node-agent **and** install the AllowlistSynchronizer. |
| `nodeAgent.gke.allowlist.name` | `armo-kubescape-node-agent-<minor>` | Allowlist to match / sync. |
| `nodeAgent.gke.allowlist.path` | `""` | Synchronizer path; empty = derive from `name`. |

See also: [GKE Autopilot install guide](https://kubescape.io/docs/integrations/kubescape-integration-with-cloud-providers/running-armokubescape-node-agents-on-gke-autopilot-clusters/).
