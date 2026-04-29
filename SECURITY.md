# Security

The Kubescape project manages this document in the central project repository.

Go to the [centralized SECURITY.md](https://github.com/kubescape/project-governance/blob/main/SECURITY.md)

## Artifact Provenance

All Helm chart releases published from this repository include a signed provenance attestation generated using
[GitHub Artifact Attestations](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
(keyless signing via GitHub OIDC + Sigstore).

### Verifying a release

Download the chart tarball from the [releases page](https://github.com/kubescape/helm-charts/releases),
then verify its provenance with the [GitHub CLI](https://cli.github.com/):

```bash
gh attestation verify kubescape-operator-<version>.tgz \
  --repo kubescape/helm-charts
```

A successful verification confirms the artifact was built by a GitHub Actions workflow
within this repository and that the content matches what was produced at build time.

> **What attestation does NOT prove:** Attestation verifies build origin and provenance only.
> It does not guarantee that all tests passed, that the code was reviewed, or that the release
> is free of vulnerabilities. Always review the [release notes](https://github.com/kubescape/helm-charts/releases)
> and the relevant [security advisories](https://github.com/kubescape/helm-charts/security/advisories).

### Stricter verification (specific release workflow)

To additionally confirm the artifact was produced by the specific release workflow
(not just any workflow in this repository), add `--signer-workflow`:

```bash
# For standard releases (with E2E tests):
gh attestation verify kubescape-operator-<version>.tgz \
  --repo kubescape/helm-charts \
  --signer-workflow kubescape/helm-charts/.github/workflows/03-helm-release.yaml

# For releases published without E2E tests:
gh attestation verify kubescape-operator-<version>.tgz \
  --repo kubescape/helm-charts \
  --signer-workflow kubescape/helm-charts/.github/workflows/04-helm-release-no-tests.yaml
```

All attestations are publicly visible at
[github.com/kubescape/helm-charts/attestations](https://github.com/kubescape/helm-charts/attestations).
