# Kubescape Operator

![Version: 1.18.7](https://img.shields.io/badge/Version-1.18.7-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v1.18.7](https://img.shields.io/badge/AppVersion-v1.18.7-informational?style=flat-square)

[Kubescape operator documentation](https://kubescape.io/docs/install-operator/)
[Troubleshooting guide](https://hub.armosec.io/docs/installation-troubleshooting#3-the-kubescape-pod-restarted)

## Install

> **Warning:** We only support installing this chart using Helm or ArgoCD.
Using alternative installation methods, such as Kustomize, Helmfile or using custom scripts, may lead to unexpected behavior and issues.
We cannot guarantee compatibility or provide support for deployments that are installed using methods other than Helm or ArgoCD.

Run the install command:
```
helm repo update ; helm upgrade --install kubescape kubescape/kubescape-operator -n kubescape --create-namespace --set clusterName=`kubectl config current-context` --set capabilities.continuousScan=enable
```

Verify that the installation was successful:
```shell
$ kubectl get pods -n kubescape
kubescape     kubescape-548d6b4577-qshb5                          1/1     Running   0               60m
kubescape     kubevuln-6779c9d74b-wfgqf                           1/1     Running   0               60m
kubescape     operator-5d745b5b84-ts7zq                           1/1     Running   0               60m
kubescape     storage-59567854fd-hg8n8                            1/1     Running   0               60m
```
## View results

The scanning results will be available gradually as the scans are completed.

View your configuration scan reports:
```
kubectl get workloadconfigurationscans -A
```

View your image vulnerabilities:
```
kubectl get vulnerabilitymanifests -A
```

## Uninstall

You can uninstall this helm chart by running the following command:
```shell
helm uninstall kubescape -n kubescape
```
Then, delete the kubescape namespace:
```shell  
kubectl delete ns kubescape
```

### Adjusting Resource Usage for Your Cluster

By default, Kubescape is configured for small- to medium-sized clusters.
If you have a larger cluster and you experience slowdowns or see Kubernetes evicting components, please revise the amount of resources allocated for the troubled component.

Taking Kubescape for example, we found that our defaults of 500 MiB of memory and 500m CPU work well for clusters up to 1250 total resources.
If you have more total resources or experience resource pressure already, first check out how many resources are in your cluster by running the following command:

```
kubectl get all -A --no-headers | wc -l
```

The command should print an approximate count of resources in your cluster.
Then, based on the number you see, allocate 100 MiB of memory for every 200 resources in your cluster over the count of 1250, but no less than 128 MiB total.
The formula for memory is as follows:
```
MemoryLimit := max(128, 0.4 * YOUR_AMOUNT_OF_RESOURCES)
```

For example, if your cluster has 500 resources, a sensible memory limit would be:
```
kubescape:
  resources:
    limits:
      memory: 200Mi  # max(128, 0.4 * 500) == 200
```
If your cluster has 50 resources, we still recommend allocating at least 128 MiB of memory.

Regarding CPU, the more you allocate, the faster Kubescape will scan your cluster.
This is especially true for clusters that have a large amount of resources.
However, we recommend that you give Kubescape no less than 500m CPU no matter the size of your cluster so it can scan a relatively large amount of resources fast ;)

## Chart support

### Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| global.networkPolicy.enabled | bool | `false` | Create NetworkPolicies for all components |
| global.networkPolicy.createEgressRules | bool | `false` | Create common Egress rules for NetworkPolicies |
| global.kubescapePsp.enabled | bool | `false` | Enable all privileges in Pod Security Policies for Kubescape namespace |
| global.httpsProxy | string | `""` | Set https egress proxy for all components. Must supply also port.  |
| global.proxySecretFile | string | `""` | Set proxy certificate / RootCA for all components to be used for proxy configured in global.httpsProxy |
| customScheduling.affinity | yaml |  | Use the `affinity` sub-section to define affinity rules that will apply to all of the workloads managed by the kubescape-operator |
| customScheduling.nodeSelector | yaml | | Configure `nodeSelector` rules under the nodeSelector sub-section that will apply to all of the workloads managed by the kubescape-operator |
| customScheduling.tolerations | yaml | | Define `tolerations` in the tolerations sub-section that will apply to all of the workloads managed by the kubescape-operator |
| global.overrideRuntimePath | string | `""` | Override the runtime path for node-agent |
| credentials.cloudSecret | string | `""` | Leave it blank for the default secret. If you have an existing secret, override with the existing secret name to avoid Helm creating a default one |
| kollector.affinity | object | `{}` | Assign custom [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) rules to the StatefulSet |
| kollector.image.repository | string | `"quay.io/kubescape/kollector"` | [source code](https://github.com/kubescape/kollector) |
| kollector.nodeSelector | object | `{}` | [Node selector](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| kollector.volumes | object | `[]` | Additional volumes for the collector |
| kollector.volumeMounts | object | `[]` | Additional volumeMounts for the collector |
| kubescape.affinity | object | `{}` | Assign custom [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) rules to the deployment |
| kubescape.downloadArtifacts | bool | `true` | download policies every scan, we recommend it should remain true, you should change to 'false' when running in an air-gapped environment or when scanning with high frequency (when running with Prometheus) |
| kubescape.enableHostScan | bool | `true` | enable [host scanner feature](https://hub.armosec.io/docs/host-sensor) |
| kubescape.image.repository | string | `"quay.io/kubescape/kubescape"` | [source code](https://github.com/kubescape/kubescape/tree/master/httphandler) (public repo) |
| kubescape.nodeSelector | object | `{}` | [Node selector](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| kubescape.serviceMonitor.enabled | bool | `false` | enable/disable service monitor for prometheus (operator) integration |
| kubescape.skipUpdateCheck | bool | `false` | skip check for a newer version |
| kubescape.labels | `[]` | adds labels to the kubescape microservice |
| kubescape.submit | bool | `true` | submit results to Kubescape SaaS: https://cloud.armosec.io/ |
| kubescape.volumes | object | `[]` | Additional volumes for Kubescape |
| kubescape.volumeMounts | object | `[]` | Additional volumeMounts for Kubescape |
| kubescapeScheduler.enabled | bool | `true` | enable/disable a kubescape scheduled scan using a CronJob |
| kubescapeScheduler.image.repository | string | `"quay.io/kubescape/http_request"` | [source code](https://github.com/kubescape/http-request) (public repo) |
| kubescapeScheduler.scanSchedule | string | `"0 0 * * *"` | scan schedule frequency |
| kubescapeScheduler.volumes | object | `[]` | Additional volumes for scan scheduler |
| kubescapeScheduler.volumeMounts | object | `[]` | Additional volumeMounts for scan scheduler |
| gateway.affinity | object | `{}` | Assign custom [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) rules to the deployment |
| gateway.image.repository | string | `"quay.io/kubescape/gateway"` | [source code](https://github.com/kubescape/gateway) |
| gateway.nodeSelector | object | `{}` | [Node selector](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| gateway.volumes | object | `[]` | Additional volumes for the notification service |
| gateway.volumeMounts | object | `[]` | Additional volumeMounts for the notification service |
| kubevuln.affinity | object | `{}` | Assign custom [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) rules to the deployment |
| kubevuln.image.repository | string | `"quay.io/kubescape/kubevuln"` | [source code](https://github.com/kubescape/kubevuln) |
| kubevuln.nodeSelector | object | `{}` | [Node selector](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| kubevuln.volumes | object | `[]` | Additional volumes for the image vulnerability scanning |
| kubevuln.volumeMounts | object | `[]` | Additional volumeMounts for the image vulnerability scanning |
| kubevulnScheduler.enabled | bool | `true` | enable/disable an image vulnerability scheduled scan using a CronJob |
| kubevulnScheduler.image.repository | string | `"quay.io/kubescape/http_request"` | [source code](https://github.com/kubescape/http-request) (public repo) |
| kubevulnScheduler.scanSchedule | string | `"0 0 * * *"` | scan schedule frequency |
| kubevulnScheduler.volumes | object | `[]` | Additional volumes for scan scheduler |
| kubevulnScheduler.volumeMounts | object | `[]` | Additional volumeMounts for scan scheduler |
| operator.affinity | object | `{}` | Assign custom [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) rules to the deployment |
| operator.image.repository | string | `"quay.io/kubescape/operator"` | [source code](https://github.com/kubescape/operator) |
| operator.nodeSelector | object | `{}` | [Node selector](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| operator.volumes | object | `[]` | Additional volumes for the web socket |
| operator.volumeMounts | object | `[]` | Additional volumeMounts for the web socket |
| hostScanner.volumes | object | `[]` | Additional volumes for the host scanner |
| hostScanner.volumeMounts | object | `[]` | Additional volumeMounts for the host scanner |
| awsIamRoleArn | string | `nil` | AWS IAM arn role |
| cloudProviderMetadata.cloudRegion | string | `nil` | cloud region |
| cloudProviderMetadata.gkeProject | string | `nil` | GKE project |
| cloudProviderMetadata.gkeServiceAccount | string | `nil` | GKE service account |
| cloudProviderMetadata.aksSubscriptionID | string | `nil` | AKS subscription ID |
| cloudProviderMetadata.aksResourceGroup | string | `nil` | AKS resource group |
| cloudProviderMetadata.aksClientID | string | `nil` | AKS client ID |
| cloudProviderMetadata.aksClientSecret | string | `nil` | AKS client secret |
| cloudProviderMetadata.aksTenantID | string | `nil` | AKS tenant ID |
| volumes | object | `[]` | Additional volumes for all containers |
| volumeMounts | object | `[]` | Additional volumeMounts for all containers |
| imageScanning.privateRegistries.credentials | object | `[]` | Credentials for scanning images pulled from private container registries. This configuration is not needed when using `imagePullSecrets`|
| imageScanning.privateRegistries.credentials.registry | string | `nil` | URL of the private container registry.|
| imageScanning.privateRegistries.credentials.username | string | `nil` | Username/Client ID for authentication.|
| imageScanning.privateRegistries.credentials.password | string | `nil` | Password/Token/Client Secret for authentication.|
| imageScanning.privateRegistries.credentials.skipTlsVerify | bool | `false` | Skip TLS certificate verification |
| imageScanning.privateRegistries.credentials.insecure | bool | `false` | Use HTTP instead of HTTPS |


# In-cluster components overview

An overview of each in-cluster component which is part of the Kubescape platform helm chart.
Follow the repository link for in-depth information on a specific component.

---

## High-level Architecture Diagram

```mermaid
graph TB

  client([client]) .-> dashboard
  masterGw  .- gw

  subgraph Cluster
    gw(Gateway)
    operator(Operator)
    k8sApi(Kubernetes API);
    kubevuln(Kubevuln)
    ks(Kubescape)
    gw --- operator
    operator -->|scan cluster| ks
    operator -->|scan images| kubevuln
    operator --> k8sApi
    ks --> k8sApi
  end;
  
subgraph Backend
    er(CloudEndpoint)
    dashboard(Dashboard) --> masterGw("Master Gateway") 
    ks --> er
    kubevuln --> er
  end;
  
  classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
  classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000;
  class k8sApi k8s
  class ks,operator,gw,masterGw,kollector,kubevuln,er,dashboard plain
```

---

## [Gateway](https://github.com/kubescape/gateway)

* __Resource Kind:__ `Deployment`
* __Communication:__ REST API, Websocket
* __Responsibility:__ Broadcasts a message received to its registered clients. When a client registers itself in a Gateway it must provide a set of attributes, which will serve as identification, for message routing purposes.

  In our architecture, the Gateway acts both as a server and a client, depending on its running configuration:
  * Master Gateway: Refers to the instance running in the backend. Broadcasts messages to all of its registered Gateways.
  * In-cluster Gateway: Refers to the instance running in the cluster. Registered to the Master Gateway using a websocket; Broadcasts messages to the different in-cluster components, this enables executing actions in runtime.

  A Master Gateway communicates with multiple in-cluster Gateways, hence it is able to communicate with multiple clusters.

```mermaid
graph TB
  subgraph Backend
   dashboard(Dashboard)
    masterGw("Gateway (Master)") 
  end
   subgraph Cluster N
    gw3("Gateway (In-cluster)")
    operator3(Operator)
  end;
  subgraph Cluster 2
    gw2("Gateway (In-cluster)")
    operator2(Operator)
  end;
   
subgraph Cluster 1
    gw1("Gateway (In-cluster)")
    operator1(Operator)
  end;
  dashboard --> masterGw
   masterGw .- gw2
   masterGw .- gw3
       gw1 .- operator1
    gw2 .- operator2
    gw3 .- operator3
   masterGw .- gw1


  classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
  classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000;
  class k8sApi k8s
  class ks,operator1,dashboard,operator2,operator3 plain
```

---

## [Operator](https://github.com/kubescape/operator)

* __Resource Kind:__ `Deployment`
* __Communication:__ REST API, Websocket
* __Responsibility:__ The Operator component is at the heart of the solution as it is the triggering engine for the different actions in the cluster; It responds to REST API requests and messages received over websocket connection, and triggers the relevant action in the cluster. Such actions could be triggering a configuration scan, image vulnerability scan, defining a recurring scan (by creating CronJobs), etc.

```mermaid
graph TB
  subgraph Cluster
    gw(Gateway)
    operator(Operator)
    k8sApi(Kubernetes API);
    kubevuln(Kubevuln)
    ks(Kubescape)
    urlCm{{ConfigMap<br>URLs }}
    recurringTempCm{{ConfigMap<br>Recur. Scan Template }}
    recurringScanCj{{CronJob<br>Recurring Scan }}
  end;
   masterGw(Master Gateway) .- gw
    gw ---> operator
    recurringScanCj ---> operator
    operator -->|scan cluster| ks
    operator -->|scan images| kubevuln
    operator --> k8sApi
    operator --- urlCm
    operator --- recurringTempCm
  
  classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
  classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000;
  class k8sApi k8s
  class ks,gw,masterGw,kollector,urlCm,recurringScanCj,recurringTempCm,kubevuln,er,dashboard plain
```

---

## [Kubevuln](https://github.com/kubescape/kubevuln/)

* __Resource Kind:__ `Deployment`
* __Communication:__ REST API
* __Responsibility:__ Scans container images for vulnerabilities, using [Grype](https://github.com/anchore/grype) as its engine.

```mermaid
graph TB

subgraph Cluster
    kubevuln(Kubevuln)  
    k8sApi(Kubernetes API)
    operator(Operator)
    gateway(Gateway)
    urlCm{{ConfigMap<br>URLs }}
    recurringScanCj{{CronJob<br>Recurring Scan }}
    recurringScanCm{{ConfigMap<br>Recurring Scan }}
    recurringTempCm{{ConfigMap<br>Recurring Scan Template }}

end

masterGateway .- gateway
gateway .-|Scan Notification| operator 
operator -->|Collect NS, Images|k8sApi
operator -->|Start Scan| kubevuln
operator --- urlCm
urlCm --- kubevuln 
recurringTempCm --- operator
recurringScanCj -->|Scan Notification| operator
recurringScanCm --- recurringScanCj

subgraph Backend
    er(CloudEndpoint)
    masterGateway("Master Gateway") 
    kubevuln -->|Scan Results| er
end;

classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000

class k8sApi k8s
class urlCm,recurringScanCm,operator,er,gateway,masterGateway,recurringScanCj,recurringTempCm plain


```

---

## [Kubescape](https://github.com/kubescape/kubescape/tree/master/httphandler)

* __Resource Kind:__ `Deployment`
* __Communication:__ REST API
* __Responsibility:__ Runs [Kubescape](https://github.com/kubescape/kubescape) for detecting misconfigurations in the cluster; This is microservice uses the same engine as the Kubescape CLI tool.

```mermaid
graph TB

subgraph Cluster
    ks(Kubescape)
    k8sApi(Kubernetes API)
    operator(Operator)
    gateway(Gateway)
    ksCm{{ConfigMap<br>Kubescape }}
    recurringScanCj{{CronJob<br>Recurring Scan }}
    recurringScanCm{{ConfigMap<br>Recurring Scan }}
    recurringTempCm{{ConfigMap<br>Recurring Scan Template }}
end

masterGateway .- gateway
gateway .-|Scan Notification| operator 
operator -->|Start Scan| ks
ks-->|Collect Cluster Info|k8sApi
ksCm --- ks 
recurringTempCm --- operator
recurringScanCj -->|Scan Notification| operator
recurringScanCm --- recurringScanCj
subgraph Backend
    er(CloudEndpoint)
    masterGateway("Master Gateway") 
    ks -->|Scan Results| er
end;

classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000

class k8sApi k8s
class ksCm,recurringScanCm,operator,er,gateway,masterGateway,recurringScanCj,recurringTempCm plain


```

---

## [Kollector](https://github.com/kubescape/kollector)

* __Resource Kind:__ `StatefulSet`
* __Responsibility:__ Communicates with the Kubernetes API server to collect cluster information and watches for changes in the cluster. Information is reported to the backend via the CloudEndpoint and the Gateway.

```mermaid
graph TD
subgraph Backend
    er(CloudEndpoint)
    masterGw("Master Gateway") 
end;

subgraph Cluster
    kollector(Kollector) 
    k8sApi(Kubernetes API);
    gw(Gateway)
end;

kollector .->|Scan new image| gw
masterGw .- gw
kollector --> er
kollector --> k8sApi

classDef k8s fill:#326ce5,stroke:#fff,stroke-width:1px,color:#fff;
classDef plain fill:#ddd,stroke:#fff,stroke-width:1px,color:#000;
class k8sApi k8s
class er,gw,masterGw plain
```

---

## [URLs ConfigMap](https://github.com/kubescape/helm-charts/blob/master/charts/kubescape-operator/templates/cloudapi-configmap.yaml)

Holds a list of communication URLs. Used by the following components:

* Operator
* Kubevuln
* Gateway

<details><summary>Config Example (YAML)</summary>

```yaml
gatewayWebsocketURL: 127.0.0.1:8001                             # component: in-cluster gateway
gatewayRestURL: 127.0.0.1:8002                                  # component: in-cluster gateway
kubevulnURL: 127.0.0.1:8081                                     # component: kubevuln
kubescapeURL: 127.0.0.1:8080                                    # component: kubescape
accountID: 1111-aaaaa-4444-555
clusterName: minikube
```
</details>

---

## Kubernetes API

Some in-cluster components communicate with the Kubernetes API server for different purposes:

* Kollector

  Watches for changes in namespace, workloads, and nodes. Reports information to the CloudEndpoint. Identifies image-related changes and triggers an image scanning on the new images accordingly (scanning new images functionality is optional).

* Operator

  Creates/updates/deletes resources for recurring scan purposes (CronJobs, ConfigMaps). Collects required information (NS, image names/tags) for Kubevuln's image scanning.

* Kubescape

  Collects namespaces, workloads, RBAC etc. required for cluster scans.

---

## Backend components

The backend components are running in [Kubescape's SaaS offering](https://cloud.armosec.io/).

### Dashboard

* REST API service

### CloudEndpoint

* __Responsibility:__ Receive and process Kubescape & Kubevuln scan results.
* __Communication:__ REST API

---

## Logging and troubleshooting

Each component writes logs to the standard output.

Every action has a generated `jobId` which is written to the log.

An action which creates sub-action(s), will be created with a different `jobId` but with a `parentId` which will correlate to the parent action's `jobId`.

### Distroless images

Each component is built as a distroless image. This means that the image does not contain any shell or package manager. This is done for security reasons.

In order to troubleshoot a component, you can use the `kubectl debug` command to add an [ephemeral container](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/#ephemeral-container) to the pod and run a shell in it:

```bash
kubectl -n kubescape debug -it <pod-name> --image=docker.io/busybox --target=<container-name>
```

**Note:** The `--target` parameter must be supported by the Container Runtime.
When not supported, the Ephemeral Container may not be started, or it may be started with an isolated process namespace so that `ps` does not reveal processes in other containers.

Use `kubectl delete` to remove the Pod when you're finished (there is no other way to remove the ephemeral container):

```bash
kubectl -n kubescape delete pod <pod-name>
```

---

## Recurring scans

3 types of recurring scans are supported:

  1. Cluster configuration scanning (Kubescape)
  2. Vulnerability scanning for container images (Kubevuln)
  3. Container registry scanning (Kubevuln)

When creating a recurring scan, the Operator component will create a `ConfigMap` and a `CronJob` from a recurring template ConfigMap. Each scan type comes with a template.

The CronJob itself does not run the scan directly. When a CronJob is ready to run, it will send a REST API request to the Operator component, which will then trigger the relevant scan (similarly to a request coming from the Gateway).

The scan results are then sent by each relevant component to the CloudEndpoint.

### Main Flows Diagrams

<details><summary>Recurring Scan Creation</summary>


```mermaid
sequenceDiagram
    actor user
    participant dashboard as Backend<br><br>Dashboard
    participant masterGw as Backend<br><br>Master Gateway
    participant clusterGw as Cluster<br><br>In-Cluster Gateway
    participant operator as Cluster<br><br>Operator
    participant k8sApi as Cluster<br><br>Kubernetes API
    
    user->>dashboard: 1. create scan schedule
    dashboard->>masterGw: 2. build schedule notification
    masterGw->>clusterGw: 3. broadcast notification
    clusterGw->>operator: 4. create recurring scan
    operator->>k8sApi: 5. get namespaces, workloads
    k8sApi-->>operator: 
    operator->>k8sApi: 6. Create cronjob & ConfigMap
```
</details>

<details><summary>Recurring Image Scan</summary>

```mermaid
sequenceDiagram
   participant cronJob as Cluster<br><br>CronJob
   participant operator as Cluster<br><br>Operator
   participant k8sApi as Cluster<br><br>Kubernetes API
   participant kubeVuln as Cluster<br><br>Kubevuln
   participant er as Backend<br><br>CloudEndpoint
   loop
      cronJob->>operator: 1. run image scan
   end
   operator->>k8sApi: 2. list NS, container images
   k8sApi-->>operator: 
   operator->>kubeVuln: 3. scan images
   kubeVuln ->> er: 4. send scan results
```

</details>

<details><summary>Recurring Kubescape Scan</summary>

```mermaid
sequenceDiagram
  participant cronJob as Cluster<br><br>CronJob
  participant operator as Cluster<br><br>Operator
  participant ks as Cluster<br><br>Kubescape
  participant k8sApi as Cluster<br><br>Kubernetes API
  participant er as Backend<br><br>CloudEndpoint
  loop
      cronJob->>operator: 1. run configuration scan
  end
  operator->>ks: 2. kubescape scan 
  ks->>k8sApi: 3. list NS, workloads, RBAC 
  k8sApi->>ks: 
  ks ->> er: 4. send scan results
```

</details>

---
## Common Issues
* Error starting the container watcher - `(fanotify)`.

  This error is usually caused by the `node-agent` not being able to find `runc` in any of the default paths.
  This can be fixed by adding the path of `runc` to the global configuration [here](#values).
  If you aren't sure where `runc` is located, you can run the following command on the node to find it:
  ```bash
  find / -name runc 2>/dev/null
  ```
  In case you are in an environment where you can't access the node, one solution is to run a privileged pod on the node, and run the command from there. To create a privileged pod, run the following command:
  ```bash
   kubectl run --rm -i --tty busybox --image=busybox --restart=Never --overrides='{"spec": {"template": {"spec": {"containers": [{"securityContext": {"privileged": true} }]}}}}' -- /bin/sh
  ```
  For K3s, the `runc` binary is different from the system one, and is located in `/var/lib/rancher/k3s/data/current/bin/runc`. Given this path, the option to set during the Helm installation is (note the `/host` prefix):
  ```bash
  --set global.overrideRuntimePath="/host/var/lib/rancher/k3s/data/current/bin/runc"
  ```