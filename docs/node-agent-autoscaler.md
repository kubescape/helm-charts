# Node Agent DaemonSet Autoscaler

## Overview

The Node Agent DaemonSet Autoscaler is a feature that enables the Kubescape operator to dynamically create, size, and manage `node-agent` DaemonSets based on the actual node sizes in your Kubernetes cluster.

Instead of deploying a static DaemonSet with fixed resource requests and limits, the autoscaler:

1. **Discovers node groups** by inspecting node labels (e.g., instance types)
2. **Calculates optimal resources** based on each node group's allocatable CPU and memory
3. **Creates dedicated DaemonSets** for each node group with appropriately sized resources
4. **Continuously reconciles** to handle cluster changes (new node types, scaling events)

## Problem Statement

The `node-agent` component's resource requirements depend on the node size it runs on. The rule of thumb is:

- **CPU/Memory Requests**: ~2% of node allocatable resources
- **CPU/Memory Limits**: ~5% of node allocatable resources

This creates two challenges:

1. **Manual calculation overhead**: Users must calculate appropriate resource values for their specific node sizes
2. **Heterogeneous clusters**: Clusters with multiple node groups (e.g., `m5.large` and `m5.4xlarge`) require different resource allocations per node type, which a single static DaemonSet cannot provide

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Kubescape Operator                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   Node Agent Autoscaler                       │  │
│  │                                                               │  │
│  │  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐  │  │
│  │  │ NodeGrouper │───▶│ Template     │───▶│ DaemonSet       │  │  │
│  │  │             │    │ Renderer     │    │ Manager         │  │  │
│  │  └─────────────┘    └──────────────┘    └─────────────────┘  │  │
│  │        │                   │                    │            │  │
│  │        ▼                   ▼                    ▼            │  │
│  │  List nodes &       Load template        Create/Update/     │  │
│  │  group by label     from ConfigMap       Delete DaemonSets  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                             │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ node-agent-     │  │ node-agent-     │  │ node-agent-     │     │
│  │ m5-large        │  │ m5-xlarge       │  │ m5-4xlarge      │     │
│  │                 │  │                 │  │                 │     │
│  │ CPU: 100m/250m  │  │ CPU: 200m/500m  │  │ CPU: 400m/1000m │     │
│  │ Mem: 180Mi/450Mi│  │ Mem: 360Mi/900Mi│  │ Mem: 720Mi/1.8Gi│     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│         │                    │                    │                 │
│         ▼                    ▼                    ▼                 │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐         │
│  │  m5.large   │      │  m5.xlarge  │      │ m5.4xlarge  │         │
│  │   nodes     │      │   nodes     │      │   nodes     │         │
│  └─────────────┘      └─────────────┘      └─────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

### Reconciliation Loop

The autoscaler runs a reconciliation loop at a configurable interval (default: 5 minutes):

1. **List all nodes** in the cluster
2. **Group nodes** by the configured label (default: `node.kubernetes.io/instance-type`)
3. **For each node group**:
   - Find the smallest allocatable CPU and memory among nodes in the group
   - Calculate resource requests/limits using configured percentages
   - Clamp values to configured min/max bounds
4. **Compare with existing DaemonSets**:
   - Create new DaemonSets for new node groups
   - Update existing DaemonSets if resources changed
   - Delete orphaned DaemonSets for removed node groups

## Configuration

### Enabling the Autoscaler

Enable the autoscaler in your Helm values:

```yaml
nodeAgent:
  autoscaler:
    enabled: true
```

Or via Helm command line:

```bash
helm upgrade --install kubescape kubescape/kubescape-operator \
  --namespace kubescape \
  --create-namespace \
  --set nodeAgent.autoscaler.enabled=true
```

### Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `nodeAgent.autoscaler.enabled` | Enable the autoscaler | `false` |
| `nodeAgent.autoscaler.nodeGroupLabel` | Node label to group by | `node.kubernetes.io/instance-type` |
| `nodeAgent.autoscaler.resourcePercentages.requestCPU` | CPU request as % of node allocatable | `2` |
| `nodeAgent.autoscaler.resourcePercentages.requestMemory` | Memory request as % of node allocatable | `2` |
| `nodeAgent.autoscaler.resourcePercentages.limitCPU` | CPU limit as % of node allocatable | `5` |
| `nodeAgent.autoscaler.resourcePercentages.limitMemory` | Memory limit as % of node allocatable | `5` |
| `nodeAgent.autoscaler.minResources.cpu` | Minimum CPU request/limit | `100m` |
| `nodeAgent.autoscaler.minResources.memory` | Minimum memory request/limit | `180Mi` |
| `nodeAgent.autoscaler.maxResources.cpu` | Maximum CPU request/limit | `2000m` |
| `nodeAgent.autoscaler.maxResources.memory` | Maximum memory request/limit | `4Gi` |
| `nodeAgent.autoscaler.reconcileInterval` | How often to reconcile | `5m` |

### Full Configuration Example

```yaml
nodeAgent:
  autoscaler:
    enabled: true
    nodeGroupLabel: "node.kubernetes.io/instance-type"
    resourcePercentages:
      requestCPU: 2
      requestMemory: 2
      limitCPU: 5
      limitMemory: 5
    minResources:
      cpu: 100m
      memory: 180Mi
    maxResources:
      cpu: 2000m
      memory: 4Gi
    reconcileInterval: 5m
```

## DaemonSet Naming Convention

DaemonSets created by the autoscaler follow this naming pattern:

```
node-agent-{sanitized-label-value}
```

For example:
- Node label `node.kubernetes.io/instance-type=m5.large` → `node-agent-m5-large`
- Node label `node.kubernetes.io/instance-type=Standard_D4s_v3` → `node-agent-standard-d4s-v3`

The label value is sanitized to be DNS-1123 compliant (lowercase, alphanumeric, hyphens only).

## Labels Applied to Managed DaemonSets

Each autoscaler-managed DaemonSet includes these labels:

```yaml
labels:
  kubescape.io/managed-by: operator-autoscaler  # Identifies autoscaler ownership
  kubescape.io/node-group: <label-value>        # The node group this targets
```

## Resource Calculation Example

Given a node with:
- Allocatable CPU: 4000m (4 cores)
- Allocatable Memory: 16Gi

With default percentages (2% request, 5% limit):

| Resource | Calculation | Result |
|----------|-------------|--------|
| CPU Request | 4000m × 2% | 80m |
| CPU Limit | 4000m × 5% | 200m |
| Memory Request | 16Gi × 2% | 327Mi |
| Memory Limit | 16Gi × 5% | 819Mi |

If the calculated value falls below `minResources`, the minimum is used instead.
If it exceeds `maxResources`, the maximum is used instead.

## Deployment Modes Comparison

| Mode | Use Case | Configuration |
|------|----------|---------------|
| **Standard** | Single node type, manual sizing | `nodeAgent.autoscaler.enabled=false` (default) |
| **Multiple DaemonSets** | Manual multi-node-type setup | `nodeAgent.multipleDaemonSets.enabled=true` |
| **Autoscaler** | Automatic sizing for any cluster | `nodeAgent.autoscaler.enabled=true` |

## Monitoring

### Check Autoscaler Status

View operator logs to see autoscaler activity:

```bash
kubectl logs -n kubescape -l app=operator | grep -i autoscaler
```

Example output:
```
{"level":"info","ts":"...","msg":"starting node agent autoscaler","namespace":"kubescape","nodeGroupLabel":"node.kubernetes.io/instance-type","reconcileInterval":"5m0s"}
{"level":"info","ts":"...","msg":"reconciliation complete","nodeGroups":3,"daemonSetsCreated":1,"daemonSetsUpdated":0,"daemonSetsDeleted":0}
```

### List Managed DaemonSets

```bash
kubectl get daemonsets -n kubescape -l kubescape.io/managed-by=operator-autoscaler
```

### View DaemonSet Resources

```bash
kubectl get daemonset -n kubescape node-agent-<node-group> -o jsonpath='{.spec.template.spec.containers[0].resources}' | jq
```

## Troubleshooting

### DaemonSet Not Created

1. **Check operator logs** for errors:
   ```bash
   kubectl logs -n kubescape -l app=operator | grep -E "(error|failed)"
   ```

2. **Verify autoscaler is enabled**:
   ```bash
   kubectl get configmap -n kubescape operator -o jsonpath='{.data.config\.json}' | jq '.nodeAgentAutoscaler'
   ```

3. **Check node labels**:
   ```bash
   kubectl get nodes --show-labels | grep -i instance-type
   ```

### Resources Not As Expected

1. **Check node allocatable resources**:
   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory
   ```

2. **Verify min/max bounds** aren't clamping the calculated values

### Pods Not Scheduling

1. **Check node selector on DaemonSet**:
   ```bash
   kubectl get daemonset -n kubescape node-agent-<group> -o jsonpath='{.spec.template.spec.nodeSelector}'
   ```

2. **Verify nodes have matching labels**:
   ```bash
   kubectl get nodes -l node.kubernetes.io/instance-type=<expected-value>
   ```

## Migration from Static DaemonSet

To migrate from a static `node-agent` DaemonSet to the autoscaler:

1. **Enable the autoscaler** in your Helm values
2. **Upgrade the Helm release** - this will:
   - Remove the static `node-agent` DaemonSet
   - Create the DaemonSet template ConfigMap
   - The operator will create autoscaler-managed DaemonSets

```bash
helm upgrade kubescape kubescape/kubescape-operator \
  --namespace kubescape \
  --set nodeAgent.autoscaler.enabled=true \
  --reuse-values
```

The migration is seamless - new DaemonSet pods will be scheduled as old ones are removed.

## Architecture Details

### Components

| Component | File | Purpose |
|-----------|------|---------|
| `NodeGrouper` | `nodegrouper.go` | Groups nodes and calculates resources |
| `TemplateRenderer` | `templaterenderer.go` | Renders DaemonSet YAML from template |
| `Autoscaler` | `autoscaler.go` | Orchestrates reconciliation loop |

### Template Source

When `autoscaler.enabled=true`, Helm creates a ConfigMap containing the DaemonSet template:

```bash
kubectl get configmap -n kubescape node-agent-daemonset-template -o yaml
```

This template is mounted into the operator pod and used to render DaemonSets with dynamic values.

## Limitations

1. **Single label grouping**: Nodes are grouped by a single label. Complex node selection (multiple labels) is not supported.

2. **Uniform nodes per group**: The autoscaler assumes all nodes with the same label value have similar allocatable resources. The smallest values in the group are used for safety.

3. **No vertical pod autoscaling**: Resources are recalculated only when the reconciliation loop runs, not in response to actual pod resource usage.

## Related Documentation

- [Kubescape Node Agent](https://kubescape.io/docs/node-agent/)
- [Kubernetes DaemonSets](https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/)
- [Node Labels](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#built-in-node-labels)

