# ARMO cluster components
ARMO Vulnerability Scanning


# Installing ARMO cluster components in a Kubernetes cluster Using Helm:
=============================================================

1. Add the Vulnerability Scanning Helm Repo
```
helm repo add armo https://armosec.github.io/armo-helm/
```

2. Get Your Account ID from ARMO

3. Install the Helm Chart, use your account ID and give your cluster a name 
```
helm upgrade --install armo  armo/armo-cluster-components -n armo-system --create-namespace --set accountGuid=<my_account_guid> --set clusterName=<my_awesome_cluster_name>
```
or in Dev environment
```
helm upgrade --install armo  armo/armo-cluster-components -n armo-system --create-namespace --set accountGuid=<my_account_guid> --set clusterName=`kubectl config current-context` --set eventReceiverHttpUrl=https://report.eudev3.cyberarmorsoft.com --set postmanUrl=postman.eudev3.cyberarmorsoft.com
```
