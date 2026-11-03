# Helm-charts - CICD Workflow docs

## The CICD Pipeline types and steps:

### Updating component image tags

Component releases don't update this chart. To move components to new releases, open a PR that changes their `image.tag` in `charts/kubescape-operator/values.yaml`, together with the matching lines in `tests/__snapshot__/snapshot_test.yaml.snap` and any `README.md` text that names the default. Group components that depend on each other in the same PR so they ship together. The `pr-created` workflow runs the Helm unit tests on it.

### Releasing the chart

The release workflows create a GitHub release and publish the Helm chart for the version in `Chart.yaml`. `03-Helm chart release` runs the E2E tests first; `03-Helm chart release (Without E2E tests)` doesn't.

1. Click on the “Actions” tab and click on the ```03-Helm chart release ``` workflow on the left side.
2. Click “Run workflows” on the top of the previous runs list.
3. Select the branch you want to create a release from by specifying it using the  ```Branch```. in most cases will be the main branch
4. Click on the ```Run workflow``` green button.
