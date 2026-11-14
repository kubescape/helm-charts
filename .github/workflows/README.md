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

### Component image candidate proposals

The component image update workflow checks published GitHub releases every Monday at 04:17 UTC. It monitors node-agent, kubevuln, storage, operator, kubescape, synchronizer, and prometheus-exporter. Only newer patch releases in the current major/minor series are proposed; larger version changes are reported for manual review. It checks both Linux amd64 and arm64 image manifests. A patch version does not establish compatibility: review the upstream releases and the entire combination, including schema, protocol, and authentication dependencies.

To run a check manually, select **Component image update candidates** in Actions and run it on `main`. The `dry_run` input defaults to true; set it to false to allow a draft proposal. Dry runs and discovery failures appear in the run summary. Discovery failures, missing manifests, and failed validation prevent publication. The candidate is linted and snapshots regenerated and checked using the same pinned Helm unittest image as CI.

The workflow owns `codex/component-image-updates` and creates one draft. It stops refreshing after human review, commits, readiness changes, or description edits. Resolve or close the draft manually before continuing; never repurpose the reserved branch. If a run stops after creating the branch but before creating or updating the PR, inspect the branch and run logs; after preserving any needed changes, a maintainer can remove the orphaned branch to allow a fresh proposal. The workflow never deletes a branch. A maintainer may need to approve the ordinary PR workflow runs created by `GITHUB_TOKEN`. Neither successful Helm tests nor image availability establish runtime compatibility; use the normal maintainer release and integration process.

To disable scheduled proposals, disable the workflow in GitHub Actions or remove its schedule trigger in a reviewed change. Manual dispatch can still be used for a dry run while enabled.
