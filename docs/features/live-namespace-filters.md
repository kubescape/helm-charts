# Live namespace filters

Enable live filtering once, then edit one ConfigMap to change the namespace
selection used by Operator, Synchronizer, Kubescape HTTP scans, and Node-agent:

```yaml
namespaceFilters:
  enabled: true
  existingConfigMap: ""
includeNamespaces: "production,payments"
excludeNamespaces: ""
```

Install or upgrade the chart with these values. Initial enablement changes
startup configuration and rolls out the affected workloads. The chart creates
`kubescape-namespace-filters` in `ksNamespace`, initialized from the existing
comma-separated namespace values. With live filtering disabled (the default),
the existing startup-only configuration continues to work.
Disabling live filtering also rolls out workloads and restores selection from
the Helm include/exclude values; update those values first if live edits differ.

## Change the live selection

```sh
kubectl --namespace kubescape edit configmap kubescape-namespace-filters
```

The document must contain **both** keys, with arrays of exact namespace names:

```yaml
data:
  namespaceFilters.json: |
    {"includeNamespaces":["production","payments"],"excludeNamespaces":[]}
```

Nonempty inclusion takes precedence over exclusion. To use exclusions, clear
inclusion. To clear filtering, set both arrays to `[]`. Do not add regex fields:
the shared format must be accepted by all four consumers. Managed values must
be strings containing comma-separated DNS-label namespace names; whitespace
and empty entries are removed before the chart emits JSON arrays.

Subsequent document edits require no Helm upgrade or component restart.
Operator and Synchronizer watch the ConfigMap through the Kubernetes API.
Kubescape and Node-agent read a required directory projection at
`/etc/namespace-filters/namespaceFilters.json`. This live directory deliberately
does not use `subPath`; existing startup configuration mounts are unchanged.
Kubelet propagates projected updates eventually, and consumers can adopt an
edit at different times. Node-agent checks the file every five seconds;
Kubescape reads it when preparing new HTTP scan and metrics requests.

These are scanning defaults, not an authorization boundary. Already prepared
or running scans retain their snapshot, old reports are retained, and explicit
HTTP scan request filters retain their existing precedence. Synchronizer keeps
its existing exceptions for cluster-scoped and operator-namespace resources.
Changing filters does not itself request a new full scan. Kubevuln receives
namespace-selected workload scans from Operator; it needs no separate watcher.

When live filtering is enabled, the chart's cluster-scoped default runtime rule
binding matches all namespaces. Node-agent's live filters control monitoring;
user-created rule bindings and other eligibility checks still apply.

## Use an externally managed ConfigMap

Create the ConfigMap in `ksNamespace` **before** referencing it:

```sh
kubectl --namespace kubescape create configmap team-namespace-filters \
  --from-literal='namespaceFilters.json={"includeNamespaces":[],"excludeNamespaces":["kube-system","kubescape"]}'
```

```yaml
namespaceFilters:
  enabled: true
  existingConfigMap: team-namespace-filters
```

Helm does not create, inspect, or modify this resource. Its name must be a
Kubernetes DNS subdomain name. Offline rendering cannot validate its contents.
Legacy namespace strings do not initialize an external document.

An external ConfigMap is recommended when filters should be managed separately
from the chart. Chart-managed values remain part of the release: intentional
Helm value changes update them, and GitOps reconciliation may restore declared
contents. The managed ConfigMap also contains `helm-values-checksum`, a chart-owned
checksum of the normalized include/exclude values. Edit only
`namespaceFilters.json`. During a connected Helm upgrade, the chart optionally
reads its existing release-owned ConfigMap: unchanged declared values preserve
the document read at render time, while an intentional values change replaces it. Offline
rendering initializes from values without requiring a cluster connection; a
GitOps renderer without live lookup can therefore restore declared contents.
This preservation is chart behavior, not a guarantee from Helm's merge strategy.

### Migrate managed filters to external ownership

Never reference `kubescape-namespace-filters` through `existingConfigMap`.
That name is reserved for chart ownership: omitting a formerly managed resource
from an upgrade lets Helm delete it. The chart rejects that unsafe transition.

1. Read the **live** managed document, including any manual edits:

   ```sh
   kubectl --namespace kubescape get configmap kubescape-namespace-filters \
     -o jsonpath='{.data.namespaceFilters\.json}' > /tmp/namespaceFilters.json
   kubectl --namespace kubescape create configmap team-namespace-filters \
     --from-file=namespaceFilters.json=/tmp/namespaceFilters.json
   ```

2. Set `existingConfigMap: team-namespace-filters` and upgrade the release.
   Changing the source reference causes a rollout; Helm removes the former
   managed ConfigMap. No `helm.sh/resource-policy: keep` annotation is added.
3. Verify all enabled consumers become healthy and use the external source.
   Confirm the external document remains intact before editing its filters.

## Invalid configuration and recovery

A missing or invalid initial external document must not start unrestricted
scanning. Operator and Synchronizer wait for valid configuration through their
API watchers. Required missing volumes/keys prevent file consumers from
starting; invalid initial files fail their initialization.

After a valid document has been accepted, malformed JSON, missing required keys,
and deletion retain the last valid filters. Recreate the same
ConfigMap with a valid document to recover; API and projected-file consumers
converge independently. A pod restarted while the document is missing or invalid
must pass initial validation again.

Keep external edits within the two-array contract. Operator and Synchronizer
have additional regex capabilities that the file consumers do not support:
adding a valid regex field can cause different components to accept different
snapshots. Helm cannot prevent an out-of-contract edit to an external resource.

In dynamic mode, remove conflicting custom `namespaceFilterFile` settings,
source/namespace/config-path environment overrides, and custom mounts using
`namespace-filters` or `/etc/namespace-filters`. Render errors identify the
conflicting values path. Unrelated customization remains supported.

The chart defaults include the live-filter implementations: Operator
`v0.2.204`, Kubescape `v4.0.17`, Node-agent `v0.3.299`, and Synchronizer
`v0.0.173`. Older image overrides may not implement this feature. The optional
SBOM-scanner sidecar inherits the Node-agent image tag when its own tag is empty;
an explicitly configured sidecar tag is preserved.

See [acceptance validation](live-namespace-filters-validation.md) for reproducible
checks and their runtime proof boundaries.
