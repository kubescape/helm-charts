# Helm Charts - CI/CD Workflow Documentation

This document describes the CI/CD pipeline for the Kubescape Helm charts repository.

## Table of Contents

- [Pipeline Types](#pipeline-types)
  - [Automatically Triggered Pipeline](#automatically-triggered-by-in-cluster-component)
  - [Manual Full CI/CD Trigger](#manually-trigger-the-full-cicd-process)
  - [Manual Release Only](#manually-trigger-only-the-release-process)
- [Pipeline Diagram](#pipeline-diagram)

---

## Pipeline Types

### Automatically Triggered by In-Cluster Component

The Helm chart CI/CD runs on GitHub Actions and is typically triggered automatically by one of the in-cluster components:

- **Operator**
- **Kubevuln**

For more details about the automatic process, see the [workflows documentation](https://github.com/kubescape/workflows/blob/main/README.md).

When triggered by one of these components, the pipeline always runs on the `dev` branch and executes the following steps:

1. **Input Validation** - Check for valid input combinations to prevent incorrect configurations
2. **Update Values** - Update the `values.yaml` file according to the provided arguments
3. **Commit Changes** - Create a new commit with the changes
4. **Create PR** - Open a pull request from `dev` to `main`
5. **Run E2E Tests** - Execute end-to-end tests using `helm_branch=main` parameter against the production backend (tests run in parallel)
6. **Generate Reports** - Create a JUnit report for each test
7. **Auto-Merge** - If all tests pass, automatically merge the PR into `main`
8. **Release** - Create a new GitHub release and Helm release for the updated chart

---

### Manually Trigger the Full CI/CD Process

To manually trigger the complete CI/CD pipeline:

1. Navigate to the **Actions** tab in GitHub
2. Select the **`00-CICD-helm-chart`** workflow from the left sidebar
3. Click **"Run workflow"** at the top of the workflow runs list
4. Configure the workflow options:

   | Parameter | Description |
   |-----------|-------------|
   | **Branch** | The branch to run the workflow from (typically `dev`) |
   | **CHANGE_TAG** | Set to `true` to update the `values.yaml` file with the provided `IMAGE_TAG` and `COMPONENT_NAME` |
   | **COMPONENT_NAME** | The in-cluster component to update the tag for |
   | **IMAGE_TAG** | The new Docker image tag for the specified component |
   | **HELM_E2E_TEST** | Set to `true` to run E2E tests using `helm_branch=dev` parameter |

5. Click the green **"Run workflow"** button

---

### Manually Trigger Only the Release Process

This process runs only the release step, creating a new GitHub release and publishing the Helm charts.

> **⚠️ Warning:** Running only the release process will **not** run any E2E tests.

1. Navigate to the **Actions** tab in GitHub
2. Select the **`03-Helm chart release`** workflow from the left sidebar
3. Click **"Run workflow"** at the top of the workflow runs list
4. Select the branch to create a release from (typically `main`)
5. Click the green **"Run workflow"** button

---

## Pipeline Diagram

The following diagram illustrates the complete CI/CD pipeline flow:

![Workflow Diagram](https://raw.githubusercontent.com/kubescape/workflows/main/assets/incluster_component_flow.jpeg)

---

## Related Resources

- [Kubescape Workflows Repository](https://github.com/kubescape/workflows)
- [Helm Chart Documentation](../../charts/kubescape-operator/README.md)