# Kubescape Helm charts

* [Kubescape cloud operator](charts/kubescape-operator/README.md)
* [Kubescape & prometheus integration](charts/kubescape-prometheus-integrator/README.md)

# Helm-charts - CICD Workflow docs


## The CICD Pipeline types and steps:

### Automatically Triggered by in-cluster component

The helm chart CICD runs on GitHub Actions, and in most cases will be automatically triggered by one of the in-cluster components:
* Operator
* Kubevuln
* Kollector
* Gateway

You can find more about the automatic process of in-cluster components [here](https://github.com/kubescape/workflows/blob/main/README.md).

When the CICD will be triggered by one of them, it will run always on the ```dev``` branch and will do the following steps in this order (High-level explanation):

1. Check for valid inputs combination to prevent cases of providing incorrect inputs (most useful for manual triggers, see instructions below).
2. Update the ```values.yaml``` file according to the arguments that passed.
3. Create a new commit for the new changes.
4. Create a new PR from the ```main```
5. Run E2E tests using ```helm_branch=main``` parameter against the ARMO production backend, the tests will run as parallel jobs.
6. Create a JUnit report for every test.
7. Only if all the tests successfully passed, the PR will be automatically merged into the ```main``` branch.
8. The last step will create a new GitHub release and Helm release for the new chart.


### Manually trigger the full CICD process
If you want to manually trigger the CICD:
1. Click on the “Actions” tab and click on the ```00-CICD-helm-chart``` workflow on the left side.
2. Click “Run workflows” on the top of the previous runs list.
3. A new pop-up will appear with some options:
    * ```Branch``` - the branch you want to run the workflow from (in most cases will be the “dev” branch)
    * ```CHANGE_TAG ```- if filled (```true```) the workflows will change the ```values.yaml``` file according to the inputs you provided for ```IMAGE_TAG``` and ```COMPONENT_NAME```
    * ```COMPONENT_NAME``` - will be the in-cluster component we want to change the tag for.
    * ```IMAGE_TAG``` - the new docker image tag of the ```COMPONENT_NAME```.
    * ```HELM_E2E_TEST``` - if filled (```true```), the CICD will run the E2E Tests using ```helm_branch=dev``` parameter
4. Click on the ```Run workflow``` green button.



### Manually trigger only the release process

This process will run only the release step from the CICD and will create a new GitHub release and will be published the helm charts

1. Click on the “Actions” tab and click on the ```03-Helm chart release ``` workflow on the left side.
2. Click “Run workflows” on the top of the previous runs list.
3. Select the branch you want to create a release from by specifying it using the  ```Branch```. in most cases will be the main branch
4. Click on the ```Run workflow``` green button.

**Note that running only the release process will not run any E2E tests**

### A diagram of the full CICD pipeline:
![Workflow](https://raw.githubusercontent.com/kubescape/workflows/main/assets/incluster_component_flow.jpeg)
