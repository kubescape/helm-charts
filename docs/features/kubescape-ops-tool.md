# kubescape-ops-tool image

## What changed

The `kubescape-operator` chart previously used two separate images for operational tasks:

- `quay.io/kubescape/kubectl` — TLS certificate generation/rotation (init containers) and
  restarting the Grype offline-DB deployment after an update.
- `quay.io/kubescape/helm-release-upgrader` — a bash entrypoint that shells out to the `helm`
  CLI to auto-upgrade the `kubescape` Helm release.

Both are replaced by a single new image, `quay.io/kubescape/kubescape-ops-tool`, built as a
statically-linked Go binary on `gcr.io/distroless/static-debian13:nonroot` (no shell, no package
manager, no bundled `kubectl`/`helm`/`jq`/`openssl`). All of the behavior those tools previously
provided via shell scripts and CLI calls is reimplemented natively in Go using `client-go`, the
Helm Go SDK, and `crypto/x509`.

The image exposes four subcommands, each mapped to one of the chart's existing usage sites:

| Subcommand | Replaces | Used by |
|---|---|---|
| `certgen-create` | `scripts/certgen-create.sh` | `templates/storage/deployment.yaml`, `templates/operator/deployment.yaml` (init containers) |
| `certgen-patch` | `scripts/certgen-patch.sh` | same as above |
| `rollout-restart` | `kubectl rollout restart` via `sh -c` | `templates/grype-offline-db/cronjob.yaml` |
| `helm-upgrade` | the `helm-release-upgrader` image's bash entrypoint | `templates/autoupdater/cronjob.yaml` |

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
    tag: 0.1.0-r1
    pullPolicy: IfNotPresent
```

Any values override targeting the three removed keys must be updated to override
`kubescapeOpsTool.image` instead. This is a minor version bump (`Chart.yaml`).

`helmReleaseUpgrader.upgrade.{release,chartRepo,chartRepoURL,chartName}` is new and configurable;
its defaults reproduce the prior hardcoded behavior exactly, so a default install is unaffected.

The autoupdater cronjob's `securityContext` (`runAsUser`/`runAsGroup`/`fsGroup`) changed from
`1000` to `65532` to match the new distroless nonroot image's UID.

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
