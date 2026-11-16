#!/usr/bin/env python3
"""Check missing/invalid initial projected filters with production file consumers.

Uses only an explicitly selected ks664-live-* Kind cluster and creates a unique
test namespace. Containers retain the chart's image, environment, config mount,
and live projection, but omit host mounts and probes: invalid filters must fail
before any scanning/runtime initialization. This does not prove API watchers or
successful eBPF startup. Evidence is retained outside the repository.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time

import yaml


ROOT = Path(__file__).resolve().parents[2]


def run(args):
    output = Path(args.output or tempfile.mkdtemp(prefix="ks664-startup-evidence-"))
    output.mkdir(parents=True, exist_ok=True)
    namespace = "ks664-startup-" + str(time.time_ns())
    results = []
    created = False

    def kubectl(*command, data=None):
        process = subprocess.run(
            ["kubectl", "--kubeconfig", args.kubeconfig, *command],
            input=data, text=True, capture_output=True, timeout=60,
        )
        if process.returncode:
            raise RuntimeError(process.stderr)
        return process.stdout

    def apply(objects):
        kubectl("apply", "-f", "-", data=yaml.safe_dump_all(objects))

    def wait(check):
        deadline = time.monotonic() + args.convergence
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(2)
        raise AssertionError("startup condition did not converge")

    def snapshot():
        data = json.loads(kubectl("-n", namespace, "get", "pods", "-o", "json"))
        (output / "pods.json").write_text(json.dumps(data, indent=2))
        return data["items"]

    try:
        context = kubectl("config", "current-context").strip()
        if not context.startswith("kind-ks664-live-"):
            raise RuntimeError("only an explicitly selected ks664-live-* cluster is supported")
        apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}])
        created = True
        rendered = subprocess.check_output([
            "helm", "template", "namespace-filters-startup", str(ROOT / "charts/kubescape-operator"),
            "--namespace", namespace, "--set", "ksNamespace=" + namespace,
            "--set", "clusterName=startup-test", "--set", "namespaceFilters.enabled=true",
            "--set", "namespaceFilters.existingConfigMap=initial-filters",
            "--set", "capabilities.kubescapeOffline=enable",
            "--set", "capabilities.runtimeObservability=enable",
            "--set", "capabilities.nodeSbomGeneration=disable",
        ], text=True, timeout=60)
        docs = [doc for doc in yaml.safe_load_all(rendered) if doc]
        config = next(doc for doc in docs if doc["kind"] == "ConfigMap"
                      and doc["metadata"]["name"] == "node-agent")
        apply([config])
        pods = []
        for name, kind in [("kubescape", "Deployment"), ("node-agent", "DaemonSet")]:
            workload = next(doc for doc in docs if doc["kind"] == kind
                            and doc["metadata"]["name"] == name)
            spec = workload["spec"]["template"]["spec"]
            container = copy.deepcopy(next(c for c in spec["containers"] if c["name"] == name))
            for key in ["livenessProbe", "readinessProbe", "startupProbe", "securityContext"]:
                container.pop(key, None)
            names = {"namespace-filters"} | ({"config"} if name == "node-agent" else set())
            container["volumeMounts"] = [mount for mount in container["volumeMounts"] if mount["name"] in names]
            container["resources"] = {"requests": {"cpu": "10m", "memory": "64Mi"},
                                      "limits": {"cpu": "500m", "memory": "512Mi"}}
            pods.append({"apiVersion": "v1", "kind": "Pod", "metadata": {
                "name": name + "-initial", "namespace": namespace}, "spec": {
                    "restartPolicy": "Never", "automountServiceAccountToken": False,
                    "containers": [container], "volumes": [
                        volume for volume in spec["volumes"] if volume["name"] in names]}})
        apply(pods)

        def missing():
            items = snapshot()
            if len(items) != 2:
                return False
            events = json.loads(kubectl("-n", namespace, "get", "events", "-o", "json"))["items"]
            (output / "missing-events.json").write_text(json.dumps(events, indent=2))
            mounted = {event.get("involvedObject", {}).get("name") for event in events
                       if event.get("reason") == "FailedMount" and "initial-filters" in event.get("message", "")}
            for pod in items:
                assert all(not status.get("containerID") for status in pod["status"].get("containerStatuses", [])), \
                    "a file consumer started without its required filter projection"
            return {pod["metadata"]["name"] for pod in items} <= mounted

        wait(missing)
        (output / "missing-pods.json").write_bytes((output / "pods.json").read_bytes())
        results.append({"name": "missing-initial-file-consumers", "status": "passed",
                        "detail": "both chart projections report FailedMount; neither process started"})
        apply([{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
            "name": "initial-filters", "namespace": namespace}, "data": {"namespaceFilters.json": "{"}}])

        def invalid():
            items = snapshot()
            failed = set()
            for pod in items:
                statuses = pod["status"].get("containerStatuses", [])
                for status in statuses:
                    terminal = status.get("state", {}).get("terminated")
                    if terminal and terminal["exitCode"] != 0:
                        logs = kubectl("-n", namespace, "logs", pod["metadata"]["name"])
                        (output / (pod["metadata"]["name"] + ".log")).write_text(logs)
                        # A failure elsewhere is not proof of filter validation.
                        if "namespace" in logs.lower() and any(token in logs.lower() for token in ["filter", "unexpected eof"]):
                            failed.add(pod["metadata"]["name"])
            return {pod["metadata"]["name"] for pod in items} <= failed and len(items) == 2

        wait(invalid)
        results.append({"name": "invalid-initial-file-consumers", "status": "passed",
                        "detail": "both production processes exit nonzero during namespace-filter initialization"})
    except Exception as exc:
        results.append({"name": "startup-check", "status": "failed", "detail": str(exc)})
    finally:
        (output / "results.json").write_text(json.dumps(results, indent=2))
        if created:
            kubectl("delete", "namespace", namespace, "--wait=false")
    print(json.dumps({"evidence": str(output), "results": results}, indent=2))
    return 0 if len(results) == 2 and all(result["status"] == "passed" for result in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--output")
    parser.add_argument("--convergence", type=int, default=180)
    arguments = parser.parse_args()
    if arguments.convergence < 1:
        parser.error("convergence must be positive")
    raise SystemExit(run(arguments))
