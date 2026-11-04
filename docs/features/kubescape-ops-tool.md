# kubescape-ops-tool image

## What changed

The `kubescape-operator` chart previously used two separate images for operational tasks:

- `quay.io/kubescape/kubectl` — TLS certificate generation/rotation (init containers) and
  restarting the Grype offline-DB deployment after an update.
- `quay.io/kubescape/helm-release-upgrader` — a bash entrypoint that shells out to the `helm`
  CLI to auto-upgrade the `kubescape` Helm release.

The scan schedulers followed later: they ran `scripts/create-operator-command.sh` (bash,
`kubectl` and `jq`) on `quay.io/kubescape/kubectl` to create `OperatorCommand` objects.

Both are replaced by a single new image, `quay.io/kubescape/kubescape-ops-tool`, built as a
statically-linked Go binary on `gcr.io/distroless/static-debian13:nonroot` (no shell, no package
manager, no bundled `kubectl`/`helm`/`jq`/`openssl`). All of the behavior those tools previously
provided via shell scripts and CLI calls is reimplemented natively in Go using `client-go`, the
Helm Go SDK, and `crypto/x509`.

The image exposes five subcommands, each mapped to one of the chart's existing usage sites:

| Subcommand | Replaces | Used by |
|---|---|---|
| `certgen-create` | `scripts/certgen-create.sh` | `templates/storage/deployment.yaml`, `templates/operator/deployment.yaml` (init containers) |
| `certgen-patch` | `scripts/certgen-patch.sh` | same as above |
| `rollout-restart` | `kubectl rollout restart` via `sh -c` | `templates/grype-offline-db/cronjob.yaml` |
| `helm-upgrade` | the `helm-release-upgrader` image's bash entrypoint | `templates/autoupdater/cronjob.yaml` |
| `create-operator-command` | `scripts/create-operator-command.sh` | `templates/kubescape-scheduler/cronjob.yaml`, `templates/kubevuln-scheduler/cronjob.yaml`, and the operator's schedule templates `assets/{kubescape,kubevuln,registry-scan}-cronjob-full.yaml` |

Source and build instructions live in `images/kubescape-ops-tool/`.

## Breaking change

The three separate per-usage `image` blocks in `values.yaml` are removed with no deprecation
shim:

- `certificates.certgen.image`
- `grypeOfflineDB.rollout.image`
- `helmReleaseUpgrader.image`

They are replaced by a single shared block:

```yaml
kubescapeOpsTool:
  image:
    repository: quay.io/kubescape/kubescape-ops-tool
    tag: 0.2.0-r1
    pullPolicy: IfNotPresent
```

Any values override targeting the three removed keys must be updated to override
`kubescapeOpsTool.image` instead. This is a minor version bump (`Chart.yaml`).

`helmReleaseUpgrader.upgrade.{release,chartRepo,chartRepoURL,chartName}` is new and configurable;
its defaults reproduce the prior hardcoded behavior exactly, so a default install is unaffected.

The autoupdater cronjob's `securityContext` (`runAsUser`/`runAsGroup`/`fsGroup`) changed from
`1000` to `65532` to match the new distroless nonroot image's UID.

### Scan schedulers

The scan schedulers moved to the same image later, with no deprecation shim either. These keys
are removed:

- `kubescapeScheduler.image`
- `kubevulnScheduler.image`
- `registryScanScheduler.image`

The schedulers now use `kubescapeOpsTool.image` (`0.2.0-r1` or later, which has the
`create-operator-command` subcommand). The `operator-command-scripts` ConfigMap and the
`command-scripts` and `tmp-dir` volumes of the scheduler pods are gone.

Helm updates the chart's own `kubescape-scheduler` and `kubevuln-scheduler` CronJobs. The
operator renders the schedules it creates (`kubescape-cronjob-template`,
`kubevuln-cronjob-template` and `registry-scan-cronjob-template`) only when it creates them.
At startup, an operator with kubescape/operator#476 re-renders each of its schedules whose
containers differ from the current template. The chart pins such an operator, so the operator
restarts in the same upgrade and moves those schedules off the script. Pinning an older
operator leaves them pointing at the removed ConfigMap, and their pods do not start.

## Autoupdater behavior

The upgrader explicitly applies the target chart's defaults, then layers the release's
previous user overrides on top (`ResetThenReuseValues`). This matches Helm's behavior for
the old script's bare `helm upgrade` with no new values: prior overrides are preserved,
not discarded. It differs from `--reuse-values`, which also retains the old chart's defaults.
See [Helm's value handling](https://github.com/helm/helm/blob/v3.22.0/pkg/action/upgrade.go#L552-L589).

Overrides for the three removed image keys can remain in `helm get values`, but have no
effect; migrate them to `kubescapeOpsTool.image` as described above.

If the release no longer exists, the upgrader exits successfully before contacting the
chart repository. This preserves the old script's handling of a CronJob left after uninstall.
