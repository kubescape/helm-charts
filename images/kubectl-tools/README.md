# kubectl-tools image for issue #923

This image supplies the commands required by the certificate init containers and
the Grype offline DB rollout CronJob. The chart's current image remains in place
until a replacement is built, scanned, publicly published, and approved by the
Kubescape maintainers.

## Release sequence

1. Obtain approval for the `quay.io/kubescape/kubectl-tools` repository and create
   it as a public repository. Configure Quay to make released tags immutable.
   Configure the `quay-kubectl-tools` GitHub environment with required reviewers
   and `QUAY_USERNAME` / `QUAY_PASSWORD` secrets scoped to this repository.
2. Review and merge the image build and refresh workflows. Trigger
   `kubectl-tools image` with `publish=false`; require both architecture jobs to
   pass, including UID checks and critical-CVE scans.
3. Trigger the workflow on `main` with `publish=true`. The publish job refuses
   to overwrite the release tag or either architecture tag. Record the digest
   returned by `docker buildx imagetools inspect` and confirm both platforms and
   anonymous pulls. A registry scan runs after publication as a second check.
4. Only then open a separate chart PR changing both image defaults to the
   released tag. Add exact-image and override regression tests, update snapshots,
   and follow the chart release versioning convention.

The first proposed tag is `1.36.4-r1`. A security rebuild must use `-r2`, `-r3`,
and so on; released tags must never move. The weekly base check uses the
repository's PR token to open a PR when Alpine's 3.24 digest changes. Review its
two architecture builds and scans, bump the release tag in the image workflow,
publish, and update the chart in a separate PR. Update `KUBECTL_VERSION` and the
tag together when upgrading kubectl itself.

The refresh workflow requires the existing `GH_PERSONAL_ACCESS_TOKEN` secret
with contents and pull-request write access. Its PR must trigger the image
workflow before the base update is merged.

For local checks, run:

```sh
docker buildx build --platform linux/amd64 --load -t kubectl-tools:test -f images/kubectl-tools/Dockerfile .
docker run --rm --user 65532:65532 --read-only kubectl-tools:test /bin/sh -ec 'kubectl version --client; bash --version; jq --version; openssl version'
docker run --rm --user 100:100 --read-only kubectl-tools:test /bin/sh -ec 'kubectl rollout restart --help >/dev/null'
```

Run the equivalent arm64 checks on an arm64 host or with QEMU. The workflow is
the release gate for both platforms. Test the chart's certificate creation,
reuse, and CA patching against a disposable Kubernetes cluster before the chart
PR merges.
