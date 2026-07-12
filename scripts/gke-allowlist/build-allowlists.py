#!/usr/bin/env python3
"""Assemble the three GKE Autopilot WorkloadAllowlist files for the 1.40 charts.

Source of truth is the GKE-generated baseline (gen/generated-public.yaml et al.);
this script normalizes them into the final, submittable form:
  - metadata.name = filename stem
  - container images -> repo regex (tag-agnostic), per the approved 1.27 convention
  - env per container = union/superset across the three charts (subset-matching safe)
  - containerImageDigests appended for private-image-mirror support
"""
import os

REPO = os.path.expanduser("~/projects/workspace-gke-autopilot-approval/gke-allow-list/ARMO")
GEN = os.path.expanduser("~/projects/workspace-gke-autopilot-approval/gen")

# --- digest blocks (read from the skopeo output, re-indented under imageDigests) ---
def load_digests(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.strip().startswith("#"):
                out.append("      " + line.strip())
            elif line.strip().startswith("- "):
                out.append("      " + line.strip())
    return "\n".join(out)

KS_DIGESTS = load_digests(f"{GEN}/digests-kubescape-node-agent.txt")
ARMO_DIGESTS = load_digests(f"{GEN}/digests-armosec-node-agent.txt")

# --- canonical body (everything except metadata.name, the image regexes, digests) ---
NODE_AGENT_ENV = [
    "GOMEMLIMIT", "HOST_ROOT", "KS_LOGGER_LEVEL", "KS_LOGGER_NAME",
    "OTEL_COLLECTOR_SVC", "CLAMAV_SOCKET", "SBOM_SCANNER_SOCKET", "SCANNER_MEMORY_LIMIT",
    "NODE_NAME", "POD_NAME", "NAMESPACE_NAME", "KUBELET_ROOT", "AGENT_VERSION",
    "NodeName", "IGNORERULEBINDINGS",
]
SBOM_ENV = ["GOMEMLIMIT", "SOCKET_PATH", "HOST_ROOT", "OTEL_COLLECTOR_SVC",
            "NODE_NAME", "POD_NAME", "NAMESPACE", "CLUSTER_NAME"]


def env_block(names, indent):
    pad = " " * indent
    return "\n".join(f"{pad}- name: {n}" for n in names)


def build(name, node_agent_img, sbom_img, clamav_img, na_digests, sbom_digests):
    return f"""apiVersion: auto.gke.io/v1
kind: WorkloadAllowlist
minGKEVersion: 1.32.0-gke.1000000
metadata:
  name: {name}
  annotations:
    autopilot.gke.io/no-connect: "true"
exemptions:
  # Node Agent monitors all processes/containers on the node, so it needs the host PID namespace.
  - autogke-disallow-hostnamespaces
  # Node Agent needs write access to parts of the host (container runtime socket, eBPF fs) for eBPF.
  - autogke-no-write-mode-hostpath
  # Node Agent needs SYS_ADMIN/SYS_PTRACE/NET_ADMIN/SYSLOG/SYS_RESOURCE/IPC_LOCK/NET_RAW for eBPF.
  - autogke-default-linux-capabilities
matchingCriteria:
  hostPID: true
  containers:
    - name: clamav
      image: {clamav_img}
      securityContext:
        capabilities:
          add:
            - SYS_PTRACE
      volumeMounts:
        - mountPath: /var/lib/clamav-tmp
          name: clamdb
        - mountPath: /run/clamav
          name: clamrun
        - mountPath: /etc/clamav
          name: etc
          readOnly: true
    - name: sbom-scanner
      image: {sbom_img}
      command:
        - /usr/bin/sbom-scanner
      env:
{env_block(SBOM_ENV, 8)}
      securityContext:
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - mountPath: /sbom-comm
          name: sbom-comm
        - mountPath: /host
          name: host
          readOnly: true
        - mountPath: /tmp
          name: sbom-scanner-tmp
    - name: node-agent
      image: {node_agent_img}
      env:
{env_block(NODE_AGENT_ENV, 8)}
      securityContext:
        capabilities:
          add:
            - SYS_ADMIN
            - SYS_PTRACE
            - NET_ADMIN
            - SYSLOG
            - SYS_RESOURCE
            - IPC_LOCK
            - NET_RAW
        privileged: false
      volumeMounts:
        - mountPath: /host
          name: host
          readOnly: true
        - mountPath: /var/lib/kubelet
          name: kubeletdir
        - mountPath: /run
          name: run
        - mountPath: /var
          name: var
          readOnly: true
        - mountPath: /lib/modules
          name: modules
          readOnly: true
        - mountPath: /sys/kernel/debug
          name: debugfs
        - mountPath: /sys/fs/cgroup
          name: cgroup
          readOnly: true
        - mountPath: /sys/fs/bpf
          name: bpffs
        - mountPath: /data
          name: data
        - mountPath: /profiles
          name: profiles
        - mountPath: /boot
          name: boot
          readOnly: true
        - mountPath: /clamav
          name: clamrun
        - mountPath: /sbom-comm
          name: sbom-comm
        - mountPath: /etc/credentials
          name: cloud-secret
          readOnly: true
        - mountPath: /etc/config/clusterData.json
          name: ks-cloud-config
          readOnly: true
          subPath: clusterData.json
        - mountPath: /etc/config/config.json
          name: config
          readOnly: true
          subPath: config.json
  securityContext:
    appArmorProfile:
      type: Unconfined
  volumes:
    - hostPath:
        path: /
      name: host
    - hostPath:
        path: /var/lib/kubelet
      name: kubeletdir
    - hostPath:
        path: /run
      name: run
    - hostPath:
        path: /var
      name: var
    - hostPath:
        path: /sys/fs/cgroup
      name: cgroup
    - hostPath:
        path: /lib/modules
      name: modules
    - hostPath:
        path: /sys/fs/bpf
      name: bpffs
    - hostPath:
        path: /sys/kernel/debug
      name: debugfs
    - hostPath:
        path: /boot
      name: boot
    - name: data
    - name: profiles
    - hostPath:
        path: /
      name: host-filesystem
    - name: clamdb
    - name: clamrun
    - configMap:
        defaultMode: 420
        name: clamav
      name: etc
    - name: sbom-comm
    - name: sbom-scanner-tmp
    - name: cloud-secret
    - configMap:
        defaultMode: 420
        name: ks-cloud-config
      name: ks-cloud-config
    - configMap:
        defaultMode: 420
        name: node-agent
      name: config
containerImageDigests:
  - containerName: node-agent
    imageDigests:
{na_digests}
  - containerName: sbom-scanner
    imageDigests:
{sbom_digests}
"""


KS = r"^quay\.io/kubescape/node-agent$"
ARMO = r"^quay\.io/(armosec|kubescape)/node-agent$"
KLAMAV = r"^quay\.io/kubescape/klamav$"

specs = [
    # (dir, name, node-agent img, sbom img, clamav img, node-agent digests, sbom digests)
    ("armo-kubescape-node-agent", "armo-kubescape-node-agent-1.40", KS, KS, KLAMAV, KS_DIGESTS, KS_DIGESTS),
    ("armo-private-node-agent",   "armo-private-node-agent-1.40",   ARMO, ARMO, KLAMAV, ARMO_DIGESTS, ARMO_DIGESTS),
    # Rapid7: node-agent uses armosec; sbom-scanner image rendered as kubescape (chart-values gap),
    # both covered by the armosec|kubescape regex. Digests: node-agent=armosec, sbom-scanner=kubescape.
    ("armo-rapid7-node-agent",    "armo-rapid7-node-agent-1.40",    ARMO, ARMO, KLAMAV, ARMO_DIGESTS, KS_DIGESTS),
]

for d, name, na, sbom, clam, nad, sbd in specs:
    outdir = f"{REPO}/{d}/1.40"
    os.makedirs(outdir, exist_ok=True)
    path = f"{outdir}/{name}.yaml"
    with open(path, "w") as f:
        f.write(build(name, na, sbom, clam, nad, sbd))
    print(f"wrote {path} ({sum(1 for _ in open(path))} lines)")
