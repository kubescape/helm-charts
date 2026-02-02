### CRDs location inside the chart tree
These CRDs are placed in the `templates/` directory instead of the standard `crds/` directory to allow Helm to manage their full lifecycle. 
This ensures they are updated during `helm upgrade` and removed during `helm uninstall`, supporting the evolving sensing capabilities of the node-agent.
No need to install them before kubescape operator chart since they are about to be used only after node-agent is up and running.

### tech debt
1. move CRDs group from `kubescape.cloud` to `kubescape.io`