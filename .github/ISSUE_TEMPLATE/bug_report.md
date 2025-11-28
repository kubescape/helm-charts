---
name: Bug report
about: Create a report to help us improve
title: ''
labels: 'bug'
assignees: ''

---

# Description
<!-- A clear and concise description of what the bug is. -->

# Environment

**Kubernetes:**
- Distribution: ` ` <!-- e.g., EKS, GKE, AKS, OpenShift, k3s, minikube -->
- Version: ` ` <!-- output of `kubectl version --short` -->

**Helm:**
- Version: ` ` <!-- output of `helm version --short` -->

**Kubescape Operator:**
- Chart Version: ` ` <!-- output of `helm list -n kubescape` -->
- App Version: ` ` <!-- from Chart.yaml or `helm list -n kubescape` -->

**Component Versions (if relevant):**
<!-- You can get these by running: kubectl get pods -n kubescape -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}' -->
- Operator: ` `
- Kubescape: ` `
- Kubevuln: ` `
- Node Agent: ` `
- Storage: ` `

**Operating System:**
- OS: ` ` <!-- the OS + version you're running kubectl from, e.g., Ubuntu 22.04 LTS, macOS 14.0 -->

# Steps To Reproduce
<!--
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error
-->

# Expected behavior
<!-- A clear and concise description of what you expected to happen. -->

# Actual Behavior
<!-- A clear and concise description of what happened. If applicable, add screenshots to help explain your problem. -->

# Logs
<!-- If applicable, include relevant logs from the affected component(s). You can get logs using:
kubectl logs -n kubescape <pod-name>
-->

<details>
<summary>Component Logs</summary>

```
Paste logs here
```

</details>

# Additional context
<!-- Add any other context about the problem here. -->