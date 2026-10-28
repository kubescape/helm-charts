# Sandbox policy CRDs

These four native Kubernetes CRDs are served by kube-apiserver and stored in
etcd, not by the storage aggregated API server. They are rendered unconditionally,
including when storage, node-agent or host sensors are disabled. Installing their
schemas does not enable enforcement.

They live in `templates/` so Helm upgrades can update their schemas. Unlike
node-agent sensing CRDs, all four carry `helm.sh/resource-policy: keep`: deleting
policy CRDs also deletes authored policies, classes and node status. The annotation
asks Helm to retain them when an uninstall, upgrade or rollback would delete them;
it does not protect against direct Kubernetes deletion. Retention can leave
orphaned resources, so reinstalling or changing release ownership needs deliberate
handling. See the chart README's upgrade guidance before migrating existing CRDs;
rendered ownership metadata does not automatically adopt existing resources.

## Updating the schemas

`kubescape/storage/artifacts/sandboxpolicy/*.crd.yaml` is the canonical generated
source (`go run ./hack/sandbox-crds` in storage). Copy schema changes from there;
maintain only Helm lifecycle/ownership metadata and this header locally. Do not
hand-edit or template `.spec`, and do not keep a second copy under `crds/`.

After building the chart dependencies, run:

```sh
helm unittest -f tests/sandbox_policy_crds_test.yaml charts/kubescape-operator
helm template sandbox-review charts/kubescape-operator \
  --namespace sandbox-review-ns --kube-version 1.28.15 > /tmp/sandbox-chart.yaml
```

No `--include-crds` is needed. Compare parsed YAML, not source bytes: select the
four rendered CRDs by `metadata.name`, assert exactly one of each, and compare each
entire `.spec` with its corresponding canonical storage manifest for exact
structural equality. Repeat with storage, all node-agent capabilities and host
sensors disabled. The unit tests also lock names, scopes, versions, retention and
release ownership metadata.
