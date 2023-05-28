# openssl req -x509 -new -nodes -keyout nginx-proxy.key -out nginx-proxy.crt -config san_scr.cnf -extensions req_ext -days 365
# kubectl delete secret nginx-proxy-tls
# kubectl create secret tls nginx-proxy-tls --cert=nginx-proxy.crt --key=nginx-proxy.key
# kubectl apply -f ./nginx.cm.yaml
# kubectl apply -f ./nginx.deploy.yaml
# kubectl apply -f ./nginx.svc.yaml
# kubectl rollout restart deployment nginx-proxy
# kubectl delete pod nginx-reg
# kubectl apply -f ./reg.nginx.yaml
# kubectl exec -it nginx-reg -- bash
# http_proxy=https://nginx-proxy.default curl -vik --proxy-cacert /etc/nginx-proxy/tls/tls.crt google.com

# helm upgrade --install -n kubescape kubescape /home/bez/projects/helm-charts/charts/kubescape-cloud-operator --set environment=dev --create-namespace --set account=2ce5daf4-e28d-4e6e-a239-03fda048070b --set global.httpsProxy='https://nginx-proxy.default' --set clusterName=`kubectl config current-context` --set addRevisionLabel=true --debug

# kubectl -n kubescape create secret generic kubescape-proxy-tls-certificate --from-file=nginx-proxy.crt=nginx-proxy.crt
kubectl -n kubescape patch deployment operator -p '{
  "spec": {
    "template": {
      "spec": {
        "volumes": [
          {
            "name": "kubescape-proxy-tls-certificate",
            "secret": {
              "secretName": "kubescape-proxy-tls-certificate",
              "items": [
                {
                  "key": "nginx-proxy.crt",
                  "path": "nginx-proxy.crt"
                }
              ]
            }
          }
        ],
        "containers": [
          {
            "name": "operator",
            "volumeMounts": [
              {
                "name": "kubescape-proxy-tls-certificate",
                "mountPath": "/etc/ssl/certs/",
                "subPath": "nginx-proxy.crt"
              }
            ]
          }
        ]
      }
    }
  }
}'
