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

## Reproduce CI

CI uses the immutable image below. Use it when checking or updating snapshots,
since a different Helm/unittest renderer can produce different config checksums.

```sh
docker run --rm --volume "$(pwd)":/apps \
  helmunittest/helm-unittest@sha256:28ea86c3e0b07f501f0c2e9c08b9f41e240f4a4b571cb5106b36cf0f0607e989 \
  charts/kubescape-operator/
```

For intentional snapshot changes, add `-u` before the chart path and review the
diff. Run again without `-u` before committing.
