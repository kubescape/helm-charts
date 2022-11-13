# Sneeffer

![Version: 0.0.1]
![AppVersion: v0.0.1]

## [Docs](https://hub.armosec.io/docs/installation-of-armo-in-cluster)

## Installing Kubescape Operator in a Kubernetes cluster using Helm:

1. Add the Kubescape Helm Repo
```
helm repo add kubescape https://kubescape.github.io/helm-charts/
```

2. Update helm repo
```
helm repo update
```

3. Install the Helm Chart, use your account ID and give your cluster a name 

Otherwise, get the account ID from the [kubescape SaaS](https://hub.armosec.io/docs/installation-of-armo-in-cluster#install-a-pre-registered-cluster)

Run the install command:
```
helm upgrade --install kubescape kubescape/kubescape-sneeffer -n kubescape --create-namespace --set account=<my_account_ID> --set clusterName=`kubectl config current-context` --set enabled=true
``