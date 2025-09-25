# Kubescape Helm Plugin

A Helm plugin that integrates with [Kubescape](https://github.com/kubescape/kubescape) to perform security scanning on Helm charts.

This plugin renders Helm charts using `helm template` and then runs Kubescape security scans on the resulting Kubernetes manifests. It supports all standard Helm chart arguments including `--values`, `--set`, and `--set-string` flags.

## Features

- 🔍 **Security Scanning**: Scan Helm charts for security vulnerabilities and misconfigurations
- 📦 **Chart Templating**: Automatically renders charts with user-provided values and overrides
- 🎯 **Flexible Input**: Supports local charts, chart archives, and remote chart repositories
- ⚙️ **Configurable**: Pass custom arguments to both Helm and Kubescape
- 📊 **Multiple Outputs**: Support for different output formats and result preservation
- 🌍 **Cross-Platform**: Works on Linux, macOS, and Windows (via WSL)

## Installation

### Prerequisites

- [Helm](https://helm.sh/docs/intro/install/) v3.0+
- [Kubescape](https://github.com/kubescape/kubescape) (automatically installed if not present)

### Install the Plugin

```bash
# Install from this repository
helm plugin install https://github.com/kubescape/helm-charts/helm-kubescape

# Or install from local directory
helm plugin install ./helm-kubescape
```

### Verify Installation

```bash
helm plugin list
helm kubescape --help
```

## Usage

### Basic Usage

```bash
# Scan a local chart
helm kubescape ./my-chart

# Scan a chart with custom values
helm kubescape ./my-chart --values values.yaml

# Scan a chart with set overrides
helm kubescape ./my-chart --set image.tag=latest

# Scan a remote chart
helm kubescape bitnami/nginx --repo https://charts.bitnami.com/bitnami
```

### Advanced Usage

```bash
# Scan with custom kubescape arguments
helm kubescape ./my-chart --kubescape-args "--severity high,critical"

# Keep manifests and specify output directory
helm kubescape ./my-chart --keep-manifests --output-dir ./scan-results

# Verbose output
helm kubescape ./my-chart --verbose

# Custom release name and namespace
helm kubescape ./my-chart --release-name my-release --namespace my-namespace
```

### Available Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--help`, `-h` | Show help message | `helm kubescape --help` |
| `--version` | Show plugin version | `helm kubescape --version` |
| `--verbose`, `-v` | Enable verbose output | `helm kubescape ./chart --verbose` |
| `--values` | Specify values in a YAML file | `helm kubescape ./chart --values values.yaml` |
| `--set` | Set values on the command line | `helm kubescape ./chart --set key=value` |
| `--set-string` | Set STRING values on the command line | `helm kubescape ./chart --set-string key=value` |
| `--set-file` | Set values from files | `helm kubescape ./chart --set-file key=path` |
| `--release-name` | Release name for the chart | `helm kubescape ./chart --release-name my-app` |
| `--namespace` | Namespace scope for the chart | `helm kubescape ./chart --namespace production` |
| `--kubescape-args` | Additional arguments for kubescape | `helm kubescape ./chart --kubescape-args "--format json"` |
| `--keep-manifests` | Keep rendered manifests after scanning | `helm kubescape ./chart --keep-manifests` |
| `--output-dir` | Directory to save results and manifests | `helm kubescape ./chart --output-dir ./results` |
| `--repo` | Chart repository URL | `helm kubescape chart --repo https://charts.example.com` |

## Examples

### Scanning Different Chart Sources

```bash
# Local chart directory
helm kubescape ./my-application

# Chart archive
helm kubescape ./my-app-1.0.0.tgz

# Remote chart from repository
helm kubescape prometheus-community/prometheus \
  --repo https://prometheus-community.github.io/helm-charts

# Chart with multiple value files
helm kubescape ./my-app \
  --values values-base.yaml \
  --values values-prod.yaml
```

### Custom Configurations

```bash
# Scan only critical and high severity issues
helm kubescape ./my-app \
  --kubescape-args "--severity critical,high"

# Save results in JSON format
helm kubescape ./my-app \
  --output-dir ./security-reports \
  --kubescape-args "--format json"

# Use specific framework for scanning
helm kubescape ./my-app \
  --kubescape-args "--framework nsa,mitre"
```

### CI/CD Integration

```bash
# Example for CI/CD pipeline
helm kubescape ./charts/my-app \
  --values ./charts/my-app/values-prod.yaml \
  --kubescape-args "--fail-threshold 7 --format junit" \
  --output-dir ./test-results
```

## Output

The plugin provides colored output for better readability:

- 🔵 **INFO**: General information messages
- 🟢 **SUCCESS**: Successful operations
- 🟡 **WARNING**: Warnings and non-critical issues
- 🔴 **ERROR**: Error messages

### Exit Codes

- `0`: Scan completed successfully with no issues
- `1`: Plugin error (missing dependencies, invalid arguments, etc.)
- `>1`: Kubescape found security issues (exit code depends on Kubescape configuration)

## Troubleshooting

### Common Issues

#### Kubescape Not Found
```bash
# Install kubescape manually
curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh | /bin/bash

# Or download from releases page
# https://github.com/kubescape/kubescape/releases
```

#### Chart Rendering Issues
```bash
# Test chart rendering separately
helm template my-release ./my-chart --values values.yaml

# Check chart dependencies
helm dependency update ./my-chart
```

#### Permission Issues
```bash
# Ensure plugin script is executable
chmod +x $HOME/.local/share/helm/plugins/helm-kubescape/kubescape.sh
```

### Verbose Mode

Use the `--verbose` flag to get detailed information about what the plugin is doing:

```bash
helm kubescape ./my-chart --verbose
```

This will show:
- Helm template command being executed
- Kubescape scan command being executed
- File paths for manifests and results
- Additional debugging information

## Contributing

Contributions are welcome! Please see the [Contributing Guide](../CONTRIBUTING.md) for details.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](../LICENSE) file for details.

## Related Projects

- [Kubescape](https://github.com/kubescape/kubescape) - Open-source Kubernetes security scanner
- [Helm](https://github.com/helm/helm) - The Kubernetes Package Manager
- [Kubescape Operator](../charts/kubescape-operator/) - Kubescape operator for continuous scanning