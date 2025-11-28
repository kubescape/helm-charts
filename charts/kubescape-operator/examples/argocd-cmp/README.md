# ArgoCD Config Management Plugin for Helm Lookup Support

This example demonstrates how to use an ArgoCD Config Management Plugin (CMP) to enable
Helm's `lookup` function for the Kubescape Operator chart. This allows the chart to
auto-discover node types and calculate resources dynamically, even when deployed via ArgoCD.

## Background

By default, ArgoCD uses `helm template` to render Helm charts, which does not support the
`lookup` function (it returns empty results). This CMP workaround runs a custom script that:

1. Queries the Kubernetes API for node information
2. Groups nodes by their labels (`kubescape.io/daemonset-group`, `node.kubernetes.io/instance-type`, etc.)
3. Calculates resource requests/limits as percentages of node capacity
4. Generates a temporary values file with the configurations
5. Passes it to `helm template`

## Prerequisites

- ArgoCD v2.4+ (CMP sidecar support)
- `kubectl`, `helm`, and `jq` available in the CMP sidecar image
- RBAC permissions for the repo-server to read nodes

## Installation

### 1. Create the CMP ConfigMap

```bash
kubectl apply -f cmp-plugin-configmap.yaml
```

### 2. Grant RBAC Permissions

The CMP sidecar needs permissions to list nodes:

```bash
kubectl apply -f rbac.yaml
```

### 3. Patch the ArgoCD Repo Server

Add the CMP sidecar to the argocd-repo-server deployment:

```bash
kubectl patch deployment argocd-repo-server -n argocd --patch-file repo-server-patch.yaml
```

Or if you're using the ArgoCD Helm chart, add this to your values:

```yaml
repoServer:
  volumes:
    - name: cmp-kubescape
      configMap:
        name: cmp-kubescape-helm-lookup
    - name: cmp-tmp
      emptyDir: {}
  extraContainers:
    - name: kubescape-helm-lookup
      image: alpine/k8s:1.31.2
      command: [/var/run/argocd/argocd-cmp-server]
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
      volumeMounts:
        - mountPath: /var/run/argocd
          name: var-files
        - mountPath: /home/argocd/cmp-server/plugins
          name: plugins
        - mountPath: /home/argocd/cmp-server/config/plugin.yaml
          subPath: plugin.yaml
          name: cmp-kubescape
        - mountPath: /tmp
          name: cmp-tmp
```

### 4. Create the ArgoCD Application

```bash
kubectl apply -f application.yaml
```

Or create it via the ArgoCD UI/CLI, specifying the plugin name `kubescape-helm-lookup-v1.0`.

## Configuration

### Resource Percentages

You can customize the resource percentages by setting environment variables in your Application:

```yaml
spec:
  source:
    plugin:
      env:
        - name: CPU_LIMIT_PERCENT
          value: "15"
        - name: CPU_REQUEST_PERCENT
          value: "8"
        - name: MEMORY_LIMIT_PERCENT
          value: "12"
        - name: MEMORY_REQUEST_PERCENT
          value: "6"
```

### Additional Helm Values

To pass additional values files or set values:

```yaml
spec:
  source:
    plugin:
      env:
        - name: HELM_VALUES
          value: |
            clusterName: my-cluster
            nodeAgent:
              image:
                tag: v1.0.0
```

## How It Works

The CMP plugin executes the following steps:

1. **Node Discovery**: Queries all nodes and extracts grouping labels
2. **Resource Calculation**: For each node group, calculates:
   - CPU limit = `allocatable.cpu * CPU_LIMIT_PERCENT / 100`
   - CPU request = `allocatable.cpu * CPU_REQUEST_PERCENT / 100`
   - Memory limit = `allocatable.memory * MEMORY_LIMIT_PERCENT / 100`
   - Memory request = `allocatable.memory * MEMORY_REQUEST_PERCENT / 100`
3. **Values Generation**: Creates a YAML configuration for `multipleDaemonSets.configurations`
4. **Helm Template**: Runs `helm template` with the generated values

## Troubleshooting

### Plugin not found

Make sure the plugin name in your Application matches `kubescape-helm-lookup-v1.0` (name + version).

### Permission denied reading nodes

Check that the RBAC resources are correctly applied:

```bash
kubectl auth can-i list nodes --as=system:serviceaccount:argocd:argocd-repo-server
```

### Empty configurations generated

Verify your nodes have one of the expected labels:
- `kubescape.io/daemonset-group`
- `node.kubernetes.io/instance-type`
- `beta.kubernetes.io/instance-type`

You can add labels manually:

```bash
kubectl label node <node-name> kubescape.io/daemonset-group=<group-name>
```

### Debug the plugin

Check the CMP sidecar logs:

```bash
kubectl logs -n argocd deployment/argocd-repo-server -c kubescape-helm-lookup
```

## Files

- `cmp-plugin-configmap.yaml` - The CMP plugin configuration
- `rbac.yaml` - RBAC permissions for node access
- `repo-server-patch.yaml` - Patch to add the CMP sidecar
- `application.yaml` - Example ArgoCD Application

## Limitations

- The plugin queries nodes at manifest generation time. If nodes change, you need to trigger a refresh/sync.
- Resource calculations use integer math, so there may be minor rounding differences.
- Only supports `Ki`, `Mi`, `Gi` memory suffixes (covers most Kubernetes distributions).

## Security Considerations

- The CMP sidecar has read-only access to node information only.
- No secrets or sensitive data are accessed.
- The sidecar runs as non-root (UID 999).