#!/usr/bin/env python3
"""Offline chart regression tests for issue #664 (helm and PyYAML required).

Run with: python3 scripts/test-live-namespace-filters.py
This suite verifies rendering, including complete-document and pod-template
stability. It does not establish live component or Kubernetes behavior.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1] / "charts/kubescape-operator"
HELM = os.environ.get("HELM", "helm")
MANAGED = "kubescape-namespace-filters"
DIRECTORY = "/etc/namespace-filters"
FILTER_FILE = DIRECTORY + "/namespaceFilters.json"
BASE = {
    "unittest": True,
    "clusterName": "namespace-filter-regression",
    "server": "fixture.invalid",
    "account": "synthetic-account",
    "accessKey": "synthetic-access-key",
    "namespaceFilters": {"enabled": True},
    "alertCRD": {"installDefault": True},
}
MODES = {
    "standard": {},
    "multiple": {"nodeAgent": {"multipleDaemonSets": {
        "enabled": True,
        "configurations": [
            {"nodeSelector": {"kubernetes.io/os": "linux"}, "resources": {
                "requests": {"cpu": "100m", "memory": "180Mi"},
                "limits": {"cpu": "500m", "memory": "1400Mi"}}},
            {"nodeSelector": {"test.example/group": "second"}, "resources": {
                "requests": {"cpu": "200m", "memory": "200Mi"},
                "limits": {"cpu": "600m", "memory": "1500Mi"}}},
        ],
    }}},
    "autoscaler": {"nodeAgent": {"autoscaler": {"enabled": True}}},
}


def merge(*items):
    result = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
    return result


def render(values=None, kube_version="1.28.0"):
    with tempfile.TemporaryDirectory(prefix="namespace-filters-render-") as temp:
        path = Path(temp) / "values.yaml"
        path.write_text(yaml.safe_dump(merge(BASE, values or {})))
        process = subprocess.run(
            [HELM, "template", "namespace-filters", str(CHART), "--namespace",
             "kubescape", "--kube-version", kube_version, "-f", str(path)],
            capture_output=True, text=True, check=False,
        )
    return process


def documents(values=None, kube_version="1.28.0"):
    process = render(values, kube_version)
    if process.returncode:
        raise AssertionError(process.stderr)
    docs = {}
    for doc in yaml.safe_load_all(process.stdout):
        if doc:
            key = (doc["kind"], doc["metadata"].get("namespace", ""), doc["metadata"]["name"])
            if key in docs:
                raise AssertionError(f"duplicate resource identity: {key}")
            docs[key] = doc
    return docs


def named(docs, kind, name):
    return next(d for key, d in docs.items() if key[0] == kind and key[2] == name)


def node_workloads(docs):
    workloads = [d for d in docs.values() if d["kind"] in ("Deployment", "DaemonSet")
                 and d["metadata"]["name"].startswith("node-agent")]
    for doc in docs.values():
        if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "node-agent-daemonset-template":
            # Preserve and compare the complete Go template separately. Its pod
            # volumes/containers precede the dynamic scheduling control blocks.
            text = doc["data"]["daemonset-template.yaml"]
            workloads.append(yaml.safe_load(text.split("\n      nodeSelector:", 1)[0]))
    return workloads


class NamespaceFilters(unittest.TestCase):
    def assert_projection(self, workload, configmap=MANAGED):
        pod = workload["spec"]["template"]["spec"]
        volume = next(v for v in pod["volumes"] if v["name"] == "namespace-filters")
        self.assertEqual(volume["configMap"]["name"], configmap)
        self.assertFalse(volume["configMap"].get("optional", False))
        self.assertIn({"key": "namespaceFilters.json", "path": "namespaceFilters.json"},
                      volume["configMap"]["items"])
        container = next(c for c in pod["containers"] if c["name"] in ("kubescape", "node-agent"))
        mount = next(m for m in container["volumeMounts"] if m["name"] == "namespace-filters")
        self.assertEqual(mount["mountPath"], DIRECTORY)
        self.assertTrue(mount["readOnly"])
        self.assertNotIn("subPath", mount)
        self.assertNotIn("subPathExpr", mount)

    def test_managed_document_and_all_consumers(self):
        docs = documents({"includeNamespaces": " alpha, ,beta, ", "excludeNamespaces": "gamma"})
        cm = named(docs, "ConfigMap", MANAGED)
        self.assertEqual(json.loads(cm["data"]["namespaceFilters.json"]), {
            "includeNamespaces": ["alpha", "beta"], "excludeNamespaces": ["gamma"]})
        self.assertNotIn("helm.sh/resource-policy", cm["metadata"].get("annotations") or {})
        for name in ("operator", "synchronizer", "node-agent"):
            config = json.loads(named(docs, "ConfigMap", name)["data"]["config.json"])
            if name == "synchronizer":
                config = config["inCluster"]
                self.assertEqual(config["namespace"], "kubescape")
            field = "namespaceFilterFile" if name == "node-agent" else "namespaceFilterConfigMapName"
            self.assertEqual(config[field], FILTER_FILE if name == "node-agent" else MANAGED)
            self.assertNotIn("includeNamespaces", config)
            self.assertNotIn("excludeNamespaces", config)
        scanner = named(docs, "Deployment", "kubescape")
        self.assert_projection(scanner)
        env = scanner["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertIn({"name": "KS_NAMESPACE_FILTERS_FILE", "value": FILTER_FILE}, env)
        self.assertFalse({e["name"] for e in env} & {"KS_INCLUDE_NAMESPACES", "KS_EXCLUDE_NAMESPACES"})
        binding = named(docs, "RuntimeRuleAlertBinding", "all-rules-all-pods")
        self.assertEqual(binding["spec"]["namespaceSelector"], {})

    def test_empty_filters_clear_both_lists(self):
        docs = documents({"includeNamespaces": " , ", "excludeNamespaces": ""})
        self.assertEqual(json.loads(named(docs, "ConfigMap", MANAGED)["data"]["namespaceFilters.json"]),
                         {"includeNamespaces": [], "excludeNamespaces": []})

    def test_external_reference_and_custom_namespace(self):
        docs = documents({"namespaceFilters": {"existingConfigMap": "security.filters-v1"},
                          "ksNamespace": "custom-security", "includeNamespaces": "alpha"})
        self.assertFalse(any(k[0] == "ConfigMap" and k[2] == MANAGED for k in docs))
        for name in ("operator", "synchronizer"):
            cm = named(docs, "ConfigMap", name)
            self.assertEqual(cm["metadata"]["namespace"], "custom-security")
            config = json.loads(cm["data"]["config.json"])
            if name == "synchronizer":
                config = config["inCluster"]
                self.assertEqual(config["namespace"], "custom-security")
            self.assertEqual(config["namespaceFilterConfigMapName"], "security.filters-v1")
        self.assert_projection(named(docs, "Deployment", "kubescape"), "security.filters-v1")
        for workload in node_workloads(docs):
            self.assert_projection(workload, "security.filters-v1")

    def test_static_mode_preserves_namespace_selection(self):
        docs = documents({"namespaceFilters": {"enabled": False}, "includeNamespaces": "alpha", "excludeNamespaces": "beta"})
        self.assertFalse(any(k[0] == "ConfigMap" and k[2] == MANAGED for k in docs))
        for name in ("operator", "synchronizer", "node-agent"):
            config = json.loads(named(docs, "ConfigMap", name)["data"]["config.json"])
            if name == "synchronizer":
                config = config["inCluster"]
            self.assertEqual(config["includeNamespaces"], "alpha")
            self.assertNotIn("excludeNamespaces", config)
            self.assertNotIn("namespaceFilterFile", config)
            self.assertNotIn("namespaceFilterConfigMapName", config)
        for workload in node_workloads(docs) + [named(docs, "Deployment", "kubescape")]:
            self.assertNotIn("namespace-filters", [v["name"] for v in workload["spec"]["template"]["spec"]["volumes"]])

    def test_every_node_mode_and_sbom_image_inheritance(self):
        for mode, values in MODES.items():
            for explicit_tag in ("", "v0.3.243"):
                with self.subTest(mode=mode, explicit_tag=explicit_tag):
                    docs = documents(merge(values, {"nodeAgent": {"sbomScanner": {
                        "enabled": True, "image": {"tag": explicit_tag}}}}))
                    workloads = node_workloads(docs)
                    self.assertEqual(len(workloads), 2 if mode == "multiple" else 1)
                    for workload in workloads:
                        self.assert_projection(workload)
                        containers = workload["spec"]["template"]["spec"]["containers"]
                        self.assertEqual(next(c for c in containers if c["name"] == "node-agent")["image"],
                                         "quay.io/kubescape/node-agent:v0.3.244")
                        self.assertEqual(next(c for c in containers if c["name"] == "sbom-scanner")["image"],
                                         "quay.io/kubescape/node-agent:" + (explicit_tag or "v0.3.244"))

    def test_only_filter_data_changes_in_every_mode(self):
        for mode, values in MODES.items():
            with self.subTest(mode=mode):
                before = documents(merge(values, {"includeNamespaces": "alpha", "excludeNamespaces": "gamma"}))
                after = documents(merge(values, {"includeNamespaces": "beta", "excludeNamespaces": "delta"}))
                self.assertEqual(before.keys(), after.keys())
                changed = []
                for key in before:
                    if before[key] != after[key]:
                        changed.append(key)
                    if key[0] in ("Deployment", "DaemonSet"):
                        self.assertEqual(before[key]["spec"]["template"], after[key]["spec"]["template"], key)
                    if key[0] == "ConfigMap" and key[2] == "node-agent-daemonset-template":
                        self.assertEqual(before[key]["data"]["daemonset-template.yaml"],
                                         after[key]["data"]["daemonset-template.yaml"])
                self.assertEqual(changed, [("ConfigMap", "kubescape", MANAGED)])
                before_cm = named(before, "ConfigMap", MANAGED)
                after_cm = named(after, "ConfigMap", MANAGED)
                self.assertNotEqual(before_cm.pop("data"), after_cm.pop("data"))
                self.assertEqual(before_cm, after_cm)

    def test_invalid_value_types_and_names(self):
        invalid = [
            {"namespaceFilters": "enabled"},
            {"namespaceFilters": {"enabled": None}},
            {"namespaceFilters": {"enabled": "true"}},
            {"namespaceFilters": {"enabled": 1}},
            {"namespaceFilters": {"existingConfigMap": 12}},
            {"namespaceFilters": {"existingConfigMap": MANAGED}},
            {"namespaceFilters": {"existingConfigMap": "Bad_Name"}},
            {"namespaceFilters": {"existingConfigMap": "a..b"}},
            {"namespaceFilters": {"existingConfigMap": "-filters"}},
            {"namespaceFilters": {"existingConfigMap": "filters."}},
            {"namespaceFilters": {"existingConfigMap": "a" * 254}},
            {"includeNamespaces": ["alpha"]},
            {"excludeNamespaces": True},
            {"includeNamespaces": "alpha.*"},
            {"excludeNamespaces": "Uppercase"},
            {"includeNamespaces": "a" * 64},
            {"includeNamespaces": "alpha.beta"},
        ]
        for values in invalid:
            with self.subTest(values=values):
                process = render(values)
                self.assertNotEqual(process.returncode, 0, process.stdout)
                self.assertRegex(process.stderr, r"namespaceFilters|includeNamespaces|excludeNamespaces")

    def test_dns_name_boundaries(self):
        external = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61])
        self.assertEqual(len(external), 253)
        docs = documents({"namespaceFilters": {"existingConfigMap": external},
                          "includeNamespaces": "a" * 63})
        self.assert_projection(named(docs, "Deployment", "kubescape"), external)

    def test_mount_and_config_override_conflicts(self):
        invalid = [
            {"nodeAgent": {"config": {"extra": {"namespaceFilterFile": "/other"}}}},
            {"nodeAgent": {"config": {"extra": {"NamespaceFilterFile": "/other"}}}},
        ]
        for owner in (None, "nodeAgent", "kubescape"):
            for field, value in (
                ("volumes", [{"name": "namespace-filters", "emptyDir": {}}]),
                ("volumeMounts", [{"name": "other", "mountPath": DIRECTORY}]),
                ("volumeMounts", [{"name": "other", "mountPath": FILTER_FILE}]),
                ("volumeMounts", [{"name": "namespace-filters", "mountPath": "/different"}]),
                ("volumeMounts", [{"name": "other", "mountPath": DIRECTORY + "/nested"}]),
                ("volumeMounts", [{"name": "other", "mountPath": DIRECTORY + "/./"}]),
            ):
                invalid.append({owner: {field: value}} if owner else {field: value})
        for values in invalid:
            with self.subTest(values=values):
                process = render(values)
                self.assertNotEqual(process.returncode, 0, process.stdout)
                self.assertIn("namespaceFilters", process.stderr)

    def test_environment_source_conflicts(self):
        sources = {
            "nodeAgent": ("NAMESPACEFILTERFILE", "CONFIG_DIR"),
            "operator": ("NAMESPACEFILTERCONFIGMAPNAME", "NAMESPACE"),
            "synchronizer": ("CONFIG", "CLUSTER_CONFIG", "INCLUSTER.NAMESPACEFILTERCONFIGMAPNAME", "INCLUSTER.NAMESPACE"),
            "kubescape": ("KS_NAMESPACE_FILTERS_FILE",),
        }
        for component, names in sources.items():
            for name in names:
                with self.subTest(component=component, name=name):
                    process = render({component: {"env": [{"name": name, "value": "override"}]}})
                    self.assertNotEqual(process.returncode, 0, process.stdout)
                    self.assertIn("namespaceFilters", process.stderr)
                    self.assertIn(name, process.stderr)

    def test_disabled_consumers_allow_unused_overrides(self):
        documents({"capabilities": {
            "operator": "disable", "configurationScan": "disable", "relevancy": "disable",
            "runtimeObservability": "disable", "networkPolicyService": "disable",
            "runtimeDetection": "disable", "malwareDetection": "disable",
            "nodeProfileService": "disable", "seccompProfileService": "disable"},
            "server": "", "operator": {"env": [{"name": "NAMESPACE", "value": "other"}]},
            "kubescape": {"env": [{"name": "KS_NAMESPACE_FILTERS_FILE", "value": "/unused"}]},
            "nodeAgent": {"config": {"extra": {"namespaceFilterFile": "/unused"}}},
            "synchronizer": {"env": [{"name": "CONFIG", "value": "unused"}]}})

    def test_api_watchers_have_no_reserved_file_mount(self):
        documents({component: {
            "volumes": [{"name": "namespace-filters", "emptyDir": {}}],
            "volumeMounts": [{"name": "namespace-filters", "mountPath": DIRECTORY}],
        } for component in ("operator", "synchronizer")})

    def test_sbom_sidecar_volume_conflict(self):
        process = render({"nodeAgent": {"sbomScanner": {
            "enabled": True,
            "volumes": [{"name": "namespace-filters", "emptyDir": {}}],
        }}})
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertIn("namespaceFilters", process.stderr)
        # An inactive sidecar's unused overrides cannot collide with the pod.
        documents({"nodeAgent": {"sbomScanner": {
            "enabled": False,
            "volumes": [{"name": "namespace-filters", "emptyDir": {}}],
        }}})

    def test_unrelated_overrides_remain_supported(self):
        # Operator CONFIG loads cluster metadata, not the watcher namespace/source.
        documents({"nodeAgent": {"config": {"extra": {"customField": "value"}}},
                   "volumes": [{"name": "custom-data", "emptyDir": {}}],
                   "volumeMounts": [{"name": "custom-data", "mountPath": "/etc/namespace-filters-backup"}],
                   "operator": {"env": [{"name": "UNRELATED_SETTING", "value": "yes"},
                                        {"name": "CONFIG", "value": "/custom/clusterData.json"}]},
                   "synchronizer": {"env": [{"name": "UNRELATED_SETTING", "value": "yes"}]}})

    def test_rbac_and_external_filter_changes_are_stable(self):
        before = documents({"namespaceFilters": {"existingConfigMap": "external-filter"}, "includeNamespaces": "alpha"})
        after = documents({"namespaceFilters": {"existingConfigMap": "external-filter"}, "includeNamespaces": "beta"})
        self.assertEqual(before, after)
        static = documents({"namespaceFilters": {"enabled": False}})
        for key in before:
            if key[0] in ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"):
                self.assertEqual(before[key], static[key], key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
