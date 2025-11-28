# Unit Tests

This directory contains unit tests for the Kubescape Operator Helm chart using the [helm-unittest](https://github.com/helm-unittest/helm-unittest) plugin.

## Prerequisites

- [Helm](https://helm.sh/docs/intro/install/) v3.x or later
- [helm-unittest](https://github.com/helm-unittest/helm-unittest) plugin

## Installation

Install the helm-unittest plugin:

```bash
helm plugin install https://github.com/helm-unittest/helm-unittest.git
```

## Running Tests

Run all tests from the repository root:

```bash
helm unittest charts/kubescape-operator/
```

Or from the chart directory:

```bash
cd charts/kubescape-operator
helm unittest .
```

### Verbose Output

For more detailed test output:

```bash
helm unittest -v charts/kubescape-operator/
```

## Updating Test Snapshots

When you make changes to the chart templates that intentionally alter the rendered output, update the test snapshots:

```bash
helm unittest -u charts/kubescape-operator/
```

> **Note:** Always review snapshot changes before committing to ensure they reflect intended modifications.

## Test Structure

Tests are organized in the `tests/` directory with the following structure:

```
tests/
├── README.md                    # This file
├── <component>_test.yaml        # Test files for specific components
└── __snapshot__/                # Snapshot files for snapshot testing
```

Each test file typically covers:

- **Default values**: Verify templates render correctly with default configuration
- **Custom values**: Test various configuration combinations
- **Edge cases**: Validate behavior with unusual or boundary inputs
- **Required fields**: Ensure required values are properly validated

## Writing New Tests

Test files should follow the naming convention `<component>_test.yaml`. Example test structure:

```yaml
suite: test <component>
templates:
  - templates/<component>.yaml
tests:
  - it: should render with default values
    asserts:
      - isKind:
          of: Deployment

  - it: should set custom image tag
    set:
      <component>.image.tag: custom-tag
    asserts:
      - equal:
          path: spec.template.spec.containers[0].image
          value: <expected-image>:custom-tag
```

For more information on writing tests, see the [helm-unittest documentation](https://github.com/helm-unittest/helm-unittest#readme).

## Continuous Integration

These tests are automatically run as part of the CI/CD pipeline to ensure chart integrity before releases.