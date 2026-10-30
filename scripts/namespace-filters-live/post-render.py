#!/usr/bin/env python3
"""Test-only interception of Operator's Kubevuln dispatch destination.

Production Operator, namespace filters and pod wiring remain unmodified. The
recorder proves dispatch selection, not successful vulnerability scanning.
"""
import json
import sys

import yaml


objects = [obj for obj in yaml.safe_load_all(sys.stdin) if obj]
for obj in objects:
    if obj and obj.get("kind") == "ConfigMap" and obj["metadata"]["name"] == "ks-cloud-config":
        config = json.loads(obj["data"]["clusterData"])
        config["kubevulnURL"] = "namespace-filter-fixture:8080"
        config["vulnScanURL"] = "namespace-filter-fixture:8080"
        obj["data"]["clusterData"] = json.dumps(config)
yaml.safe_dump_all(objects, sys.stdout)
