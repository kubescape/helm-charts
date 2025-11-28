# Kubescape Helm Charts

[![License](https://img.shields.io/github/license/kubescape/helm-charts)](https://github.com/kubescape/helm-charts/blob/main/LICENSE)
[![CNCF](https://img.shields.io/badge/CNCF-Incubating-blue)](https://www.cncf.io/projects/kubescape/)

Helm charts for deploying [Kubescape](https://kubescape.io/) components in Kubernetes clusters.

Kubescape is an open-source Kubernetes security platform that provides comprehensive security coverage, from left to right across the entire development and deployment lifecycle. It offers hardening, posture management, runtime security, and vulnerability scanning.

## Available Charts

| Chart | Description |
|-------|-------------|
| [kubescape-operator](charts/kubescape-operator/README.md) | The main Kubescape operator chart for in-cluster security scanning and runtime protection |

## Quick Start

Add the Kubescape Helm repository:

```bash
helm repo add kubescape https://kubescape.github.io/helm-charts/
helm repo update
```

Install the Kubescape operator:

```bash
helm upgrade --install kubescape kubescape/kubescape-operator \
  -n kubescape \
  --create-namespace \
  --set clusterName=$(kubectl config current-context)
```

For detailed installation options and configuration, see the [kubescape-operator README](charts/kubescape-operator/README.md).

## Documentation

- [Kubescape Documentation](https://kubescape.io/docs/)
- [Operator Installation Guide](https://kubescape.io/docs/install-operator/)
- [Chart Configuration Options](charts/kubescape-operator/README.md#values)

## Community

- [Community Resources](COMMUNITY.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## Governance

- [Governance](GOVERNANCE.md)
- [Maintainers](MAINTAINERS.md)
- [Adopters](ADOPTERS.md)

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.