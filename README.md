# ARMO cluster components
ARMO Vulnerability Scanning


# Installing ARMO cluster components in a Kubernetes cluster Using Helm:

1. Add the Vulnerability Scanning Helm Repo
```
helm repo add armo https://armosec.github.io/armo-helm/
```

2. Update helm repo
```
helm repo update
```

3. Install the Helm Chart, use your account ID and give your cluster a name 
```
helm upgrade --install armo  armo/armo-cluster-components -n armo-system --create-namespace --set accountGuid=<my_account_guid> --set clusterName=`kubectl config current-context` --set clientID=<generated client id> --set secretKey=<generated secret key>
```

 
## Values
* `accountGuid` - account ID [required]
* `clusterName` - cluster name [required]
* `clientID` - api token client ID 
* `secretKey` - api token secret key
