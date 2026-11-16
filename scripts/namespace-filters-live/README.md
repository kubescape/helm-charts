# namespace-filters-live

Live acceptance script (`run.py`) for namespace filters on a kind cluster.

The kubescape in-cluster API requires `Authorization: Bearer <token>` with a
service-account token for audience `kubescape.io`. The script requests one once per run with
`kubectl create token operator -n kubescape --audience kubescape.io` and sends it on its API calls.
Set `KS_API_AUTH_DISABLED=true` only when the cluster runs with `global.apiAuth.enabled=false`. This variable skips the token request in the script. It does not disable API authentication on the cluster.
