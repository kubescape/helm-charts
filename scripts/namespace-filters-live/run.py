#!/usr/bin/env python3
"""Run isolated Helm/production-image namespace-filter checks; retain JSON evidence.

Requires Python 3 + PyYAML, helm, kubectl, kind, podman and openssl. Never targets
the user's current kube context. Exit 1 means a failed or unverified criterion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

import yaml


ROOT = Path(__file__).resolve().parents[2]
NS = "kubescape"
FIXTURE = "namespace-filter-fixture"
MANAGED = "kubescape-namespace-filters"
EXTERNAL = "acceptance-external-filters"
NAMESPACES = ["filter-a", "filter-b"]


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.output = Path(args.output or tempfile.mkdtemp(prefix="ks664-evidence-"))
        self.output.mkdir(parents=True, exist_ok=True)
        self.kubeconfig = self.output / "kubeconfig"
        self.env = dict(os.environ, KIND_EXPERIMENTAL_PROVIDER="podman",
                        KUBECONFIG=str(self.kubeconfig))
        self.processes = []
        self.results = []
        self.result_lock = threading.Lock()
        (self.output / "results.json").write_text("[]")
        self.values = {}
        self.initial_pods = None
        self.cluster_created = False
        self.log = (self.output / "commands.log").open("w")

    def command(self, *args, data=None, timeout=240):
        # Command arguments include paths and synthetic identifiers only.
        self.log.write("$ " + " ".join(map(str, args)) + "\n")
        self.log.flush()
        result = subprocess.run(list(map(str, args)), input=data, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=self.env, timeout=timeout)
        self.log.write(result.stdout + result.stderr)
        self.log.flush()
        if result.returncode:
            raise RuntimeError(f"{args[0]} {args[1]} failed: {result.stderr[-2000:]}")
        return result.stdout

    def kubectl(self, *args, **kwargs):
        return self.command("kubectl", "--kubeconfig", self.kubeconfig, *args, **kwargs)

    def apply(self, *objects):
        self.kubectl("apply", "-f", "-", data=yaml.safe_dump_all(objects))

    def note(self, name, status, detail):
        with self.result_lock:
            self.results.append({"name": name, "status": status, "detail": detail})
            print(f"{status.upper()}: {name}: {detail}", flush=True)
            (self.output / "results.json").write_text(json.dumps(self.results, indent=2))

    def checkpoint(self, name, operation):
        try:
            operation()
        except Exception as exc:
            self.note(name, "failed", str(exc))
            return False
        self.note(name, "passed", "assertions satisfied")
        return True

    def until(self, check, timeout=None):
        duration = timeout or self.args.convergence
        end = time.monotonic() + duration
        error = None
        while time.monotonic() < end:
            try:
                result = check()
                if result:
                    return result
            except Exception as exc:
                error = exc
            time.sleep(3)
        raise AssertionError(f"did not converge within {duration}s: {error}")

    def setup(self):
        if self.args.existing_kubeconfig:
            # Reuse only an explicitly supplied, dedicated cluster created for this test.
            self.kubeconfig.write_bytes(Path(self.args.existing_kubeconfig).read_bytes())
            context = self.kubectl("config", "current-context").strip()
            if context != "kind-" + self.args.cluster or not self.args.cluster.startswith("ks664-live-"):
                raise RuntimeError("existing kubeconfig must select the matching ks664-live-* cluster")
        else:
            self.command("kind", "create", "cluster", "--name", self.args.cluster,
                         "--image", self.args.node_image, "--kubeconfig", self.kubeconfig,
                         "--wait", "180s", timeout=300)
            self.cluster_created = True
        self.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NS}},
                   *[{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n}}
                     for n in NAMESPACES])
        self.apply(*[{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "filter-subject", "namespace": n},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "filter-subject"}},
            "template": {"metadata": {"labels": {"app": "filter-subject"}}, "spec": {"containers": [
                {"name": "pause", "image": "registry.k8s.io/pause:3.10"}]}}}} for n in NAMESPACES])
        cert, key = self.output / "fixture.crt", self.output / "fixture.key"
        if not cert.exists() or not key.exists():
            self.command("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                         "-keyout", key, "-out", cert, "-days", "1", "-subj", f"/CN={FIXTURE}",
                         "-addext", f"subjectAltName=DNS:{FIXTURE},DNS:{FIXTURE}.{NS}.svc")
        secret = self.kubectl("-n", NS, "create", "secret", "tls", FIXTURE,
                              "--cert", cert, "--key", key, "--dry-run=client", "-o", "json")
        self.kubectl("apply", "-f", "-", data=secret)
        # Reusing an explicitly dedicated cluster may replace its fixture CA.
        # Recreate the fixture and roll consumers once before taking a baseline.
        self.kubectl("-n", NS, "delete", "pod", FIXTURE, "--ignore-not-found",
                     "--grace-period=0", "--force")
        self.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": FIXTURE, "namespace": NS},
                    "data": {"fixture.py": (Path(__file__).parent / "fixture.py").read_text()}},
                   {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": FIXTURE, "namespace": NS,
                    "labels": {"app": FIXTURE}}, "spec": {"containers": [{"name": "fixture",
                    "image": self.args.fixture_image, "command": ["python3", "/code/fixture.py"],
                    "ports": [{"containerPort": 8443}, {"containerPort": 8080}],
                    "volumeMounts": [{"name": "code", "mountPath": "/code", "readOnly": True},
                                     {"name": "tls", "mountPath": "/tls", "readOnly": True}]}],
                    "volumes": [{"name": "code", "configMap": {"name": FIXTURE}},
                                {"name": "tls", "secret": {"secretName": FIXTURE}}]}},
                   {"apiVersion": "v1", "kind": "Service", "metadata": {"name": FIXTURE, "namespace": NS},
                    "spec": {"selector": {"app": FIXTURE}, "ports": [
                        {"name": "tls", "port": 8443, "targetPort": 8443},
                        {"name": "http", "port": 8080, "targetPort": 8080}]}})
        self.kubectl("-n", NS, "wait", "pod/" + FIXTURE, "--for=condition=Ready", "--timeout=180s")
        self.fixture_port = self.forward("service/" + FIXTURE, 8443)
        self.values = {
            "clusterName": self.args.cluster, "namespaceFilters": {"enabled": True},
            "defaultFrameworks": ["nsa"],
            "includeNamespaces": NAMESPACES[0], "excludeNamespaces": "",
            "server": FIXTURE + ":8443", "account": "00000000-0000-4000-8000-000000000664",
            "accessKey": "synthetic-acceptance-key-only",
            "capabilities": {"kubescapeOffline": "enable", "admissionController": "disable",
                "nodeScan": "disable", "nodeSbomGeneration": "disable", "relevancy": "disable",
                "networkPolicyService": "disable", "networkEventsStreaming": "disable",
                "nodeProfileService": "disable", "httpDetection": "disable",
                "seccompProfileService": "disable", "runtimeDetection": "enable"},
            "global": {"overrideDefaultCaCertificates": {"enabled": True,
                        "caCertificates": cert.read_text()}},
            "configurations": {"persistence": "disable"},
            "kubescape": {"downloadArtifacts": False, "skipUpdateCheck": True},
            "operator": {"triggerSecurityFramework": False, "podScanGuardTime": "1s"},
            "nodeAgent": {"config": {"learningPeriod": "10s", "updatePeriod": "5s",
                                      "hostSensor": {"enabled": False}}},
        }
        self.upgrade()
        self.kubectl("-n", NS, "rollout", "restart", "deployment/operator",
                     "deployment/synchronizer", "deployment/kubescape")

    def upgrade(self):
        path = self.output / "values.yaml"
        path.write_text(yaml.safe_dump(self.values))
        self.command("helm", "upgrade", "--install", "namespace-filter-acceptance",
                     ROOT / "charts/kubescape-operator", "--namespace", NS,
                     "--kubeconfig", self.kubeconfig, "-f", path, "--timeout", "180s",
                     "--post-renderer", Path(__file__).parent / "post-render.py")

    def forward(self, resource, remote):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        log = (self.output / f"forward-{port}.log").open("w")
        process = subprocess.Popen(["kubectl", "--kubeconfig", str(self.kubeconfig), "-n", NS,
            "port-forward", resource, f"{port}:{remote}"], stdout=log, stderr=log, env=self.env)
        self.processes.append(process)
        self.until(lambda: "Forwarding from" in (self.output / f"forward-{port}.log").read_text())
        return port

    def request(self, port, path, body=None, tls=False):
        request = urllib.request.Request(f"{'https' if tls else 'http'}://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        # Fixture certificate is generated by this harness and only reached over loopback.
        with urllib.request.urlopen(request, context=ssl._create_unverified_context() if tls else None,
                                    timeout=self.args.convergence) as response:
            return response.read().decode()

    def events(self):
        return json.loads(self.request(self.fixture_port, "/events", tls=True))

    def filters(self, include=None, exclude=None, raw=None, name=MANAGED):
        value = raw if raw is not None else json.dumps({"includeNamespaces": include or [],
                                                       "excludeNamespaces": exclude or []})
        self.kubectl("-n", NS, "patch", "configmap", name, "--type=merge", "-p",
                     json.dumps({"data": {"namespaceFilters.json": value}}))

    def pods(self):
        data = json.loads(self.kubectl("-n", NS, "get", "pods", "-o", "json"))
        return {p["metadata"]["name"]: {"uid": p["metadata"]["uid"],
                "restarts": {c["name"]: c["restartCount"] for c in p["status"].get("containerStatuses", [])}}
                for p in data["items"] if any(p["metadata"]["name"].startswith(n + "-")
                    for n in ["operator", "synchronizer", "kubescape"])
                and p["status"].get("phase") != "Succeeded"}

    def ready(self):
        for name in ["operator", "synchronizer", "kubescape"]:
            self.kubectl("-n", NS, "rollout", "status", "deployment/" + name,
                         f"--timeout={self.args.startup_timeout}s", timeout=self.args.startup_timeout + 10)
        self.initial_pods = self.pods()
        (self.output / ("pod-baseline-" + str(time.time_ns()) + ".json")).write_text(
            json.dumps(self.initial_pods, indent=2))
        self.scan_port = self.forward("service/kubescape", 8080)
        self.operator_port = self.forward("service/operator", 4002)
        self.until(lambda: any(e["kind"] == "websocket-connected" for e in self.events()))

    def sync_probe_once(self, allowed, excluded):
        marker = "probe-" + str(time.time_ns())
        start = time.time()
        self.apply(*[{"apiVersion": "v1", "kind": "Service", "metadata": {"name": marker, "namespace": n},
                     "spec": {"ports": [{"port": 80}]}} for n in NAMESPACES])
        def received():
            events = [e["value"] for e in self.events() if e["kind"] == "sync" and e["time"] >= start]
            namespaces = {v.get("Namespace") for v in events if isinstance(v, dict) and v.get("Name") == marker}
            assert not (namespaces & set(excluded)), f"excluded Synchronizer events: {namespaces}"
            return set(allowed) <= namespaces
        try:
            self.until(received, timeout=min(10, self.args.convergence))
        finally:
            for n in NAMESPACES:
                self.kubectl("-n", n, "delete", "service", marker, "--ignore-not-found")
        return marker

    def sync_probe(self, allowed, excluded):
        markers = {self.until(lambda: self.sync_probe_once(allowed, excluded))}
        def no_excluded_events():
            assert not any(e["kind"] == "sync" and e["value"].get("Name") in markers
                           and e["value"].get("Namespace") in excluded for e in self.events()), \
                "delayed Synchronizer event from an excluded namespace"
        end = time.monotonic() + self.args.observation
        while time.monotonic() < end:
            markers.add(self.sync_probe_once(allowed, excluded))
            no_excluded_events()
        no_excluded_events()

    def scan_probe(self, allowed, excluded, label):
        body = {"targetType": "framework", "targetNames": ["nsa"], "hostScanner": False,
                "format": "json", "keepLocal": True}
        raw = self.request(self.scan_port, "/v1/scan?wait=true&keep=true&skipPersistence=true", body)
        (self.output / (label + "-scan.json")).write_text(raw)
        result = json.loads(raw)
        namespaces = set()
        def visit(value):
            if isinstance(value, dict):
                metadata = value.get("metadata", {})
                if isinstance(metadata, dict) and metadata.get("namespace") in NAMESPACES:
                    namespaces.add(metadata["namespace"])
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)
        visit(result)
        assert set(allowed) <= namespaces, f"scan result lacks allowed namespaces: {namespaces}"
        assert not (set(excluded) & namespaces), f"scan included excluded namespaces: {namespaces}"
        metrics = self.request(self.scan_port, "/v1/metrics?skipPersistence=true&frameworks=nsa")
        (self.output / (label + "-metrics.txt")).write_text(metrics)
        for namespace in allowed:
            assert 'namespace="' + namespace + '"' in metrics, f"metrics missing {namespace}"
        for namespace in excluded:
            assert 'namespace="' + namespace + '"' not in metrics, f"metrics includes {namespace}"

    def dispatch_probe(self, allowed, excluded):
        marker = "dispatch-" + str(time.time_ns())
        start = time.time()
        self.apply(*[{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": marker, "namespace": n},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": marker}},
            "template": {"metadata": {"labels": {"app": marker}}, "spec": {"containers": [
                {"name": "pause", "image": "registry.k8s.io/pause:3.10"}]}}}} for n in NAMESPACES])
        def dispatched():
            bodies = [json.dumps(e["value"]["body"]) for e in self.events()
                      if e["kind"] == "http" and e["time"] >= start
                      and e["value"]["path"].split("?", 1)[0] == "/v1/scanImage"]
            found = {n for n in NAMESPACES if any("namespace-" + n + "/deployment-" + marker in b for b in bodies)}
            assert not (found & set(excluded)), f"Operator dispatched excluded workload: {found}"
            return set(allowed) <= found
        try:
            self.until(dispatched)
            end = time.monotonic() + self.args.observation
            while time.monotonic() < end:
                assert dispatched()
                time.sleep(2)
        finally:
            for n in NAMESPACES:
                self.kubectl("-n", n, "delete", "deployment", marker, "--ignore-not-found", "--wait=false")

    def sync_transitions(self):
        cases = [("include-a", [NAMESPACES[0]], [], [NAMESPACES[0]], [NAMESPACES[1]]),
                 ("include-b", [NAMESPACES[1]], [], [NAMESPACES[1]], [NAMESPACES[0]]),
                 ("exclude-a", [], [NAMESPACES[0]], [NAMESPACES[1]], [NAMESPACES[0]]),
                 ("clear", [], [], NAMESPACES, [])]
        for name, include, exclude, allowed, excluded in cases:
            self.filters(include, exclude)
            self.behavior(allowed, excluded, name)
        self.recovery()

    def recovery(self):
        self.filters([NAMESPACES[1]])
        # File projection is asynchronous; establish the same last-valid snapshot
        # in every consumer before testing invalid documents.
        self.behavior([NAMESPACES[1]], [NAMESPACES[0]], "before-invalid")
        self.invalid_updates()
        self.filters([NAMESPACES[0]])
        self.behavior([NAMESPACES[0]], [NAMESPACES[1]], "valid-recovery")
        assert self.pods() == self.initial_pods, "live edits changed a running API/HTTP consumer's pod UID/restarts"
        (self.output / "pods-after-live-edits.json").write_text(json.dumps(self.pods(), indent=2))
        self.note("live-edits-no-restart", "passed", "Operator, Synchronizer and Kubescape UIDs/restarts unchanged; Node-agent excluded")

    def invalid_updates(self, name=MANAGED):
        for label, value, signature in [
            ("malformed", "{", "unexpected EOF"),
            ("missing-key", '{"includeNamespaces":[]}', "includeNamespaces and excludeNamespaces are required"),
            ("malformed-regex", '{"includeNamespaces":[],"excludeNamespaces":[],"includeNamespacesRegex":["["]}',
             'unknown field "includeNamespacesRegex"'),
        ]:
            started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.filters(raw=value, name=name)
            def projected_invalid():
                self.scan_probe([NAMESPACES[1]], [NAMESPACES[0]], "invalid-" + label)
                logs = self.kubectl("-n", NS, "logs", "deployment/kubescape", "--since-time", started)
                for line in logs.splitlines():
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if record.get("msg") == "cannot reload namespace filters; retaining last valid filters" \
                            and signature in record.get("error", ""):
                        return True
                return False
            # Corroborate that the file consumer actually saw this invalid
            # variant; rapid updates must not pass on a stale valid projection.
            self.until(projected_invalid)
            self.behavior([NAMESPACES[1]], [NAMESPACES[0]], "invalid-" + label)

    def behavior(self, allowed, excluded, label):
        def scan_observed():
            self.until(lambda: self.scan_probe(allowed, excluded, label) or True)
            end = time.monotonic() + self.args.observation
            while time.monotonic() < end:
                self.scan_probe(allowed, excluded, label)
        # Independent consumers observe the same immutable phase concurrently.
        # Await all observations before publishing the next filter document.
        checks = [
            ("synchronizer-" + label, lambda: self.sync_probe(allowed, excluded)),
            ("operator-dispatch-" + label,
             lambda: self.until(lambda: self.dispatch_probe(allowed, excluded) or True)),
            ("kubescape-" + label, scan_observed),
        ]
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self.checkpoint, name, operation) for name, operation in checks]
            results = [future.result() for future in futures]
        assert all(results), f"one or more {label} behavioral checks failed"

    def lifecycle(self):
        self.filters([NAMESPACES[1]])
        before = json.loads(self.kubectl("-n", NS, "get", "configmap", MANAGED, "-o", "json"))["data"]
        self.upgrade()
        after = json.loads(self.kubectl("-n", NS, "get", "configmap", MANAGED, "-o", "json"))["data"]
        assert before == after, "unchanged Helm upgrade reset live edits"
        self.note("upgrade-preserves-live-edit", "passed", "unchanged values preserve live ConfigMap data")
        self.values["includeNamespaces"] = ",".join(NAMESPACES)
        self.upgrade()
        data = json.loads(self.kubectl("-n", NS, "get", "configmap", MANAGED, "-o", "json"))["data"]
        assert json.loads(data["namespaceFilters.json"])["includeNamespaces"] == NAMESPACES
        self.behavior(NAMESPACES, [], "upgrade-changed-values")
        assert self.pods() == self.initial_pods, "filter-value Helm upgrade changed pod identity or restart counts"
        (self.output / "pods-after-filter-value-upgrade.json").write_text(json.dumps(self.pods(), indent=2))
        self.note("upgrade-filter-values-no-restart", "passed", "component pod UIDs and restart counts unchanged")
        self.values["namespaceFilters"]["existingConfigMap"] = MANAGED
        try:
            self.upgrade()
            raise AssertionError("same-name ownership transition unexpectedly succeeded")
        except RuntimeError as exc:
            assert "existingConfigMap" in str(exc), str(exc)
        assert json.loads(self.kubectl("-n", NS, "get", "configmap", MANAGED, "-o", "json"))["data"] == data
        self.note("unsafe-ownership-transition-rejected", "passed", "render rejected before the managed resource changed")
        self.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": EXTERNAL, "namespace": NS},
                    "data": data})
        self.values["namespaceFilters"]["existingConfigMap"] = EXTERNAL
        self.upgrade()
        self.ready()  # Changing source is a documented rollout.
        assert not self.kubectl("-n", NS, "get", "configmap", MANAGED, "--ignore-not-found").strip()
        assert json.loads(self.kubectl("-n", NS, "get", "configmap", EXTERNAL, "-o", "json"))["data"] == data
        self.behavior(NAMESPACES, [], "external")
        self.kubectl("-n", NS, "delete", "configmap", EXTERNAL)
        self.behavior(NAMESPACES, [], "external-deletion-last-valid")
        self.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": EXTERNAL, "namespace": NS},
                    "data": {"namespaceFilters.json": json.dumps({"includeNamespaces": [NAMESPACES[0]], "excludeNamespaces": []})}})
        self.behavior([NAMESPACES[0]], [NAMESPACES[1]], "external-recreation-recovery")
        external_data = json.loads(self.kubectl("-n", NS, "get", "configmap", EXTERNAL, "-o", "json"))["data"]
        self.upgrade()
        assert json.loads(self.kubectl("-n", NS, "get", "configmap", EXTERNAL, "-o", "json"))["data"] == external_data
        self.note("external-upgrade-retains-manual-data", "passed", "external live data untouched by unchanged upgrade")
        assert self.pods() == self.initial_pods, "external live edits restarted components"
        (self.output / "pods-after-external-edits.json").write_text(json.dumps(self.pods(), indent=2))
        self.note("external-live-edits-no-restart", "passed", "Operator, Synchronizer and Kubescape unchanged; Node-agent excluded")

    def watcher_startup(self):
        name = "acceptance-missing-initial"
        old_pods = set(self.pods())
        self.values["namespaceFilters"]["existingConfigMap"] = name
        self.upgrade()
        self.until(lambda: not (set(self.pods()) & old_pods))
        for component in ["operator", "synchronizer"]:
            self.until(lambda c=component: "waiting for valid namespace filter ConfigMap" in
                self.kubectl("-n", NS, "logs", "deployment/" + c, "--tail=100"))
        def no_callbacks(label):
            marker = "startup-" + str(time.time_ns())
            start = time.time()
            self.apply(*[{"apiVersion": "v1", "kind": "Service", "metadata": {"name": marker, "namespace": n},
                         "spec": {"ports": [{"port": 80}]}} for n in NAMESPACES])
            self.apply(*[{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": marker, "namespace": n},
                "spec": {"replicas": 1, "selector": {"matchLabels": {"app": marker}},
                "template": {"metadata": {"labels": {"app": marker}}, "spec": {"containers": [
                    {"name": "pause", "image": "registry.k8s.io/pause:3.10"}]}}}} for n in NAMESPACES])
            try:
                end = time.monotonic() + self.args.observation
                while time.monotonic() < end:
                    assert not any(marker in json.dumps(e["value"]) for e in self.events()
                                   if e["time"] >= start and e["kind"] in ("sync", "http")), label
                    time.sleep(2)
            finally:
                for n in NAMESPACES:
                    self.kubectl("-n", n, "delete", "service", marker, "--ignore-not-found")
                    self.kubectl("-n", n, "delete", "deployment", marker, "--ignore-not-found", "--wait=false")
        self.checkpoint("watchers-missing-startup-no-callbacks", lambda: no_callbacks("missing ConfigMap"))
        self.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name, "namespace": NS},
                    "data": {"namespaceFilters.json": "{"}})
        self.checkpoint("watchers-invalid-startup-no-callbacks", lambda: no_callbacks("invalid ConfigMap"))
        self.filters([NAMESPACES[0]], name=name)
        self.ready()
        self.behavior([NAMESPACES[0]], [NAMESPACES[1]], "watchers-startup-valid-recovery")

    def fresh_external_install(self):
        name = self.values["namespaceFilters"]["existingConfigMap"]
        before = json.loads(self.kubectl("-n", NS, "get", "configmap", name, "-o", "json"))["data"]
        self.command("helm", "uninstall", "namespace-filter-acceptance", "--namespace", NS,
                     "--kubeconfig", self.kubeconfig, "--wait", "--timeout", "180s")
        assert json.loads(self.kubectl("-n", NS, "get", "configmap", name, "-o", "json"))["data"] == before
        self.upgrade()
        self.ready()
        assert json.loads(self.kubectl("-n", NS, "get", "configmap", name, "-o", "json"))["data"] == before
        self.behavior([NAMESPACES[0]], [NAMESPACES[1]], "fresh-external-install")

    def collect(self):
        for name, args in {"pods.json": ["get", "pods", "-o", "json"],
                           "events.txt": ["get", "events", "--sort-by=.lastTimestamp"]}.items():
            try:
                (self.output / name).write_text(self.kubectl("-n", NS, *args))
            except Exception:
                pass
        for name in ["operator", "kubescape", "synchronizer", "node-agent"]:
            try:
                (self.output / (name + ".log")).write_text(self.kubectl("-n", NS, "logs",
                    ("daemonset/" if name == "node-agent" else "deployment/") + name,
                    "--all-containers=true", "--tail=1000"))
            except Exception:
                pass
        try:
            (self.output / "fixture-events.json").write_text(json.dumps(self.events(), indent=2))
        except Exception:
            pass

    def run(self):
        try:
            self.setup()
            if self.checkpoint("production-services-ready", self.ready):
                self.checkpoint("synchronizer-transitions", self.sync_transitions)
                self.checkpoint("helm-lifecycle-and-external", self.lifecycle)
                self.checkpoint("watcher-startup-safety", self.watcher_startup)
                self.checkpoint("fresh-external-install", self.fresh_external_install)
            # Never turn readiness/log/file observations into behavioral success.
            node_logs = self.kubectl("-n", NS, "logs", "daemonset/node-agent", "--tail=100")
            if "mounting /sys/fs/bpf: operation not permitted" in node_logs:
                detail = "observed kernel validation failure: mounting /sys/fs/bpf: operation not permitted"
            else:
                detail = "runtime event/profile exclusion and readmission requires additional behavioral evidence"
            self.note("node-agent-runtime-readmission", "unverified", detail)
        except Exception as exc:
            self.note("setup", "failed", str(exc))
        finally:
            self.collect()
            for process in self.processes:
                process.terminate()
            if self.cluster_created and not self.args.keep_cluster:
                self.command("kind", "delete", "cluster", "--name", self.args.cluster)
            self.log.close()
        print("Evidence: " + str(self.output), flush=True)
        return 0 if self.results and all(r["status"] == "passed" for r in self.results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", default="ks664-live-" + str(int(time.time())))
    parser.add_argument("--existing-kubeconfig", help="explicit dedicated ks664-live-* context only; never deleted")
    parser.add_argument("--output")
    parser.add_argument("--keep-cluster", action="store_true")
    parser.add_argument("--convergence", type=int, default=180)
    parser.add_argument("--observation", type=int, default=30)
    parser.add_argument("--startup-timeout", type=int, default=600,
                        help="initial image pulls/readiness; live convergence remains separately bounded")
    parser.add_argument("--node-image", default="kindest/node:v1.34.0")
    parser.add_argument("--fixture-image", default="docker.io/library/python:3.12-alpine")
    args = parser.parse_args()
    if not args.cluster.startswith("ks664-live-") or args.convergence < 1 or args.observation < 1:
        parser.error("use a ks664-live-* cluster name and positive time windows")
    raise SystemExit(Acceptance(args).run())
