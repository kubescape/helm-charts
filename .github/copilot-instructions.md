# Kubescape Helm Charts Repository
Kubescape Helm Charts is a repository containing Helm charts for the Kubescape Kubernetes security platform. The primary chart is `kubescape-operator` which deploys a comprehensive security scanning platform including vulnerability assessment, compliance checking, and runtime security monitoring.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively
- Bootstrap and validate the repository:
  - `helm version` -- verify Helm v3.x is installed
  - `kubectl version --client` -- verify kubectl is available
  - `helm plugin install https://github.com/helm-unittest/helm-unittest.git` -- install testing plugin (takes 15-30 seconds)
  - `helm dependency build charts/kubescape-operator/` -- build chart dependencies (takes 1-2 seconds)
- Lint and validate charts:
  - `helm lint charts/kubescape-operator/` -- lint chart (takes <1 second)
  - `helm unittest charts/kubescape-operator/` -- run unit tests (takes <1 second, ~444 snapshot tests)
  - `helm template charts/kubescape-operator/ --name-template kubescape --set clusterName=test-cluster` -- validate template generation
- Package the chart:
  - `helm package charts/kubescape-operator/ --destination /tmp` -- package chart (takes <1 second)

## Validation
- Always run `helm lint charts/kubescape-operator/` before committing any changes to templates or values
- Always run `helm unittest charts/kubescape-operator/` to validate template changes don't break existing functionality (runs 444 snapshot tests in <1 second)
- Always test template generation with: `helm template charts/kubescape-operator/ --name-template kubescape --set clusterName=test-cluster --dry-run`
- Update snapshots if template changes are intentional: `helm unittest -u charts/kubescape-operator/`
- For major changes, test chart installation dry-run to validate resource generation: generates exactly 53 Kubernetes resources including:
  - 4 Deployments (operator, kubescape, storage, synchronizer)
  - 1 DaemonSet (node-agent)
  - 2 CronJobs (scheduled scans)
  - 12 ConfigMaps, 6 Services, 5 ServiceAccounts
  - Multiple RBAC resources (ClusterRoles, RoleBindings)
- **CRITICAL**: If you modify templates, ALWAYS verify the resource count remains at 53 with: `helm template charts/kubescape-operator/ --name-template kubescape --set clusterName=test-cluster | grep "^kind:" | wc -l`

## Chart Structure and Key Components
The main chart is located at `charts/kubescape-operator/` and includes:
- **Operator**: Command and control component for orchestrating scans
- **Kubescape**: Core security scanning engine for compliance and misconfigurations  
- **Kubevuln**: Vulnerability scanning component
- **Storage**: Data persistence layer
- **Synchronizer**: Data synchronization with external systems
- **Node Agent**: DaemonSet for host-level and runtime security monitoring
- **Autoupdater**: Component for automatic updates

## Dependencies
The chart has local dependencies in `charts/dependency_chart/`:
- `clustered-crds`: Cluster-scoped Custom Resource Definitions
- `namespaced-crds`: Namespace-scoped Custom Resource Definitions

## CI/CD and Testing
- GitHub Actions workflows are in `.github/workflows/`
- E2E tests run against live Kubernetes clusters using system-tests repository
- Main workflow: `00-cicd.yaml` orchestrates updates, testing, and releases
- E2E test matrix includes ~25 different test scenarios covering functionality like vulnerability scanning, compliance checking, runtime security
- Chart releases are automated via `03-helm-release.yaml`

## Important Files
- `charts/kubescape-operator/Chart.yaml` -- chart metadata and version
- `charts/kubescape-operator/values.yaml` -- default configuration values  
- `charts/kubescape-operator/templates/` -- Kubernetes resource templates
- `charts/kubescape-operator/tests/` -- unit test files
- `.github/workflows/` -- CI/CD automation

## Common Configuration
Key values to understand:
- `clusterName`: Required parameter for chart installation
- `ksNamespace`: Target namespace (default: kubescape)
- `excludeNamespaces`: Namespaces to skip during scanning
- `capabilities.*`: Feature toggles for different security capabilities

## Common Commands Reference
Quick reference for frequent operations (all commands are validated and timed):

### Complete validation workflow (takes <3 seconds total)
```bash
# Full development workflow validation 
helm version && kubectl version --client
helm dependency build charts/kubescape-operator/  # <1 second
helm lint charts/kubescape-operator/              # <1 second  
helm unittest charts/kubescape-operator/          # <1 second, 444 tests
helm template charts/kubescape-operator/ --name-template kubescape --set clusterName=test-cluster --dry-run >/dev/null
helm package charts/kubescape-operator/ --destination /tmp  # <1 second
```

### One-time setup (takes ~3 seconds)
```bash
helm plugin install https://github.com/helm-unittest/helm-unittest.git
```

### Development change validation (takes <2 seconds)
```bash
helm lint charts/kubescape-operator/
helm unittest charts/kubescape-operator/
# If intentional template changes:
helm unittest -u charts/kubescape-operator/
```

### Repository root structure
```
/home/runner/work/helm-charts/helm-charts/
├── .github/
│   └── workflows/          # CI/CD automation
├── charts/
│   ├── dependency_chart/   # Local chart dependencies
│   └── kubescape-operator/ # Main operator chart
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

### Chart directory structure  
```
charts/kubescape-operator/
├── Chart.yaml        # Chart metadata
├── values.yaml       # Default values
├── templates/        # Kubernetes manifests
├── tests/           # Unit tests
└── README.md        # Chart documentation
```

### Helm plugin validation
```bash
$ helm plugin list
NAME	VERSION	DESCRIPTION
unittest	1.0.1   Running chart unittest written in YAML
```

## Installation Example
```bash
helm repo add kubescape https://kubescape.github.io/helm-charts/
helm repo update
helm upgrade --install kubescape kubescape/kubescape-operator \
  -n kubescape --create-namespace \
  --set clusterName=`kubectl config current-context`
```

## Troubleshooting
- Chart linting issues: Check template syntax in `charts/kubescape-operator/templates/`
- Unittest failures: Review snapshots in `charts/kubescape-operator/tests/__snapshot__/`
- Template errors: Use `helm template --debug` for detailed error output
- Dependency issues: Run `helm dependency build charts/kubescape-operator/` to refresh
- Resource count changes: Expected 53 resources - if different, check for missing/added templates
- Plugin not found: Install with `helm plugin install https://github.com/helm-unittest/helm-unittest.git`

## Performance Expectations
All operations are very fast (<3 seconds total for complete validation):
- Plugin installation: ~3 seconds (one-time)
- Dependency build: <1 second  
- Chart linting: <1 second
- Unit tests: <1 second (444 snapshot tests)
- Template generation: <1 second
- Chart packaging: <1 second

Always validate changes incrementally and run the full test suite before pushing commits.