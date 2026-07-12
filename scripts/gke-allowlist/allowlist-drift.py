#!/usr/bin/env python3
"""GKE Autopilot allowlist drift detector (PoC).

Renders a chart's node-agent pod spec and checks whether its privileged surface
is still COVERED by an approved WorkloadAllowlist (subset-matching rules), so a
chart-release pipeline can classify each release without a cluster:

  no-op       - workload fully covered by the allowlist (nothing to do)
  digest-only - covered, but the running image digest isn't in containerImageDigests
                (Tier-1 action: append the digest)
  spec-drift  - workload needs a capability / env / mount / container / hostPID
                NOT present in the allowlist -> a NEW allowlist version is required
                (Tier-2 gate should block the release until one is approved)

Exit code: 0 for no-op/digest-only, 2 for spec-drift (CI-gate friendly).

Usage:
  allowlist-drift.py --chart <path> --allowlist <yaml> [--values f.yaml ...]
                     [--set k=v ...] [--wrapper] [--check-digests]
"""
import argparse, re, subprocess, sys
import yaml


def render_node_agent(chart, values, sets, wrapper):
    prefix = "kubescape-operator." if wrapper else ""
    show = ("charts/kubescape-operator/templates/node-agent/daemonset.yaml"
            if wrapper else "templates/node-agent/daemonset.yaml")
    cmd = ["helm", "template", "na", chart, "--kube-version", "1.33.0",
           "--show-only", show,
           "--set", f"{prefix}clusterName=drift",
           "--set", f"{prefix}account=00000000-0000-0000-0000-000000000000",
           "--set", f"{prefix}nodeAgent.autoscaler.enabled=false"]
    for v in values:
        cmd += ["-f", v]
    for s in sets:
        cmd += ["--set", s]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"helm template failed:\n{out.stderr}")
    return yaml.safe_load(out.stdout)


def project_container(c):
    sc = c.get("securityContext", {}) or {}
    caps = sc.get("capabilities", {}) or {}
    return {
        "image": c.get("image", ""),
        "add": set(caps.get("add", []) or []),
        "drop": set(caps.get("drop", []) or []),
        "env": {e["name"] for e in (c.get("env", []) or [])},
        "mounts": {m["mountPath"] for m in (c.get("volumeMounts", []) or [])},
        "privileged": bool(sc.get("privileged", False)),
    }


def workload_projection(ds):
    spec = ds["spec"]["template"]["spec"]
    return {
        "hostPID": bool(spec.get("hostPID", False)),
        "containers": {c["name"]: project_container(c) for c in spec["containers"]},
        "hostpaths": {v["name"]: v["hostPath"]["path"]
                      for v in spec.get("volumes", []) if "hostPath" in v},
    }


def allowlist_projection(al):
    mc = al["matchingCriteria"]
    return {
        "hostPID": bool(mc.get("hostPID", False)),
        "containers": {c["name"]: project_container(c) for c in mc.get("containers", [])},
        "hostpaths": {v["name"]: v["hostPath"]["path"]
                      for v in mc.get("volumes", []) if "hostPath" in v},
        "digests": {d["containerName"]: set(d.get("imageDigests", []))
                    for d in al.get("containerImageDigests", [])},
    }


def repo(image):
    return re.split(r"[:@]", image, maxsplit=1)[0]


def resolve_digest(image):
    out = subprocess.run(["skopeo", "inspect", f"docker://{image}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    import json
    return json.loads(out.stdout).get("Digest", "").replace("sha256:", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chart", required=True)
    ap.add_argument("--allowlist", required=True)
    ap.add_argument("--values", action="append", default=[])
    ap.add_argument("--set", dest="sets", action="append", default=[])
    ap.add_argument("--wrapper", action="store_true")
    ap.add_argument("--check-digests", action="store_true",
                    help="resolve running image digests via skopeo (network)")
    args = ap.parse_args()

    wl = workload_projection(render_node_agent(args.chart, args.values, args.sets, args.wrapper))
    al = allowlist_projection(yaml.safe_load(open(args.allowlist)))

    drift, digests_missing = [], []

    if wl["hostPID"] and not al["hostPID"]:
        drift.append("hostPID required by workload but not in allowlist")

    for name, wc in wl["containers"].items():
        ac = al["containers"].get(name)
        if ac is None:
            drift.append(f"container '{name}' not in allowlist")
            continue
        # image repo must satisfy the allowlist regex (tag-agnostic)
        if not re.match(ac["image"], repo(wc["image"])):
            drift.append(f"container '{name}': image repo {repo(wc['image'])} "
                         f"not matched by allowlist regex {ac['image']}")
        for cap in wc["add"] - ac["add"]:
            drift.append(f"container '{name}': capability {cap} not in allowlist")
        for env in wc["env"] - ac["env"]:
            drift.append(f"container '{name}': env {env} not in allowlist")
        for mp in wc["mounts"] - ac["mounts"]:
            drift.append(f"container '{name}': mountPath {mp} not in allowlist")
        if wc["privileged"] and not ac["privileged"]:
            drift.append(f"container '{name}': privileged required but allowlist has privileged:false")

    for name, path in wl["hostpaths"].items():
        if al["hostpaths"].get(name) not in (path, None):
            drift.append(f"hostPath '{name}': workload {path} != allowlist {al['hostpaths'].get(name)}")

    if args.check_digests:
        for name, wc in wl["containers"].items():
            d = resolve_digest(wc["image"])
            if d and d not in al["digests"].get(name, set()):
                digests_missing.append(f"{name}: {wc['image']} -> sha256:{d[:16]}… not in containerImageDigests")

    print(f"# drift report: {args.chart}")
    print(f"#   allowlist: {args.allowlist}")
    if drift:
        print("CLASS: spec-drift  (NEW allowlist version required)")
        for d in drift:
            print(f"  - {d}")
        sys.exit(2)
    if digests_missing:
        print("CLASS: digest-only  (append digests to existing allowlist)")
        for d in digests_missing:
            print(f"  - {d}")
        sys.exit(0)
    print("CLASS: no-op  (workload covered by approved allowlist)")
    sys.exit(0)


if __name__ == "__main__":
    main()
