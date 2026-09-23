### CRDs location inside the chart tree
These CRDs are placed in the `templates/` directory instead of the standard `crds/` directory to allow Helm to manage their full lifecycle. 
This ensures they are updated during `helm upgrade` and removed during `helm uninstall`, supporting the evolving sensing capabilities of the node-agent.
No need to install them before kubescape operator chart since they are about to be used only after node-agent is up and running.

### Host-data cleanup

With host sensors enabled, Node Agent uses the `kubescape-hostdata-gc` Lease in
`ksNamespace` to elect one collector. The leader cleans records for deleted Nodes
immediately and every `nodeAgent.config.hostSensor.interval` (default `5m`), across
all ten supported host-data kinds, including kinds whose sensors are disabled.
Per-node sensing continues independently.

An unreadable or empty complete Node inventory prevents deletion. Present Nodes,
including terminating Nodes, retain their data. Each candidate's Node is checked
again before deletion, and UID/resource-version preconditions protect records
updated or replaced since listing. Failed API operations preserve affected data
for a later sweep; a missing CRD is skipped.

Install the chart's RBAC update before or alongside the supporting Node Agent
version. The agent needs cluster-wide `delete` on the ten host-data resources and
namespaced Lease `create`, plus `get`/`update` restricted to the election Lease.
Missing election permissions prevent cleanup without stopping sensing. All agents
share these permissions; election limits work, not their authorization.

This assumes one Kubescape installation namespace per cluster. Installations in
different namespaces elect independently. Lease election is not strict fencing:
brief overlap is possible on failures, and Node checks and host-data deletion are
not atomic across resources. Cancellation and conditional deletion remain the
safeguards. No cleanup runs while no enabled agent survives.

### tech debt
1. move CRDs group from `kubescape.cloud` to `kubescape.io`