# namespace-filters-live

Live acceptance script (`run.py`) for namespace filters on a kind cluster.

Kubescape images that implement in-cluster API auth require `Authorization: Bearer <token>`
with a service-account token for audience `kubescape.io`; the image pinned in the chart today
still accepts requests without one. The script requests a token once per run with
`kubectl create token operator -n kubescape --audience kubescape.io` and sends it on its API
calls, so it works against both. Set `KS_API_AUTH_DISABLED=true` to skip the token when auth is
off on the cluster.
