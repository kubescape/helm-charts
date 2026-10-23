# UnitTests

1. Install 
```
helm plugin install https://github.com/helm-unittest/helm-unittest.git

# Using Helm v4
helm plugin install https://github.com/helm-unittest/helm-unittest.git --verify=false # See Notes in https://github.com/helm-unittest/helm-unittest#install
```
2. Run
```
helm unittest charts/kubescape-operator/
```

## Update
```
helm unittest -u charts/kubescape-operator/
```
