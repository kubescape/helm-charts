#!/usr/bin/env python3
"""Apply validated discovery results to the chart, preserving YAML formatting."""
import json
import sys
from pathlib import Path

import yaml
from discover import COMPONENTS, mapping, version

ROOT = Path(__file__).resolve().parents[2]
VALUES = ROOT / 'charts/kubescape-operator/values.yaml'
TEST = ROOT / 'charts/kubescape-operator/tests/operator_image_tag_test.yaml'


def replace_scalar(source, node, expected, replacement):
    if not isinstance(node, yaml.ScalarNode) or node.value != expected:
        raise ValueError('unexpected scalar value')
    raw = source[node.start_mark.index:node.end_mark.index]
    if raw not in (expected, '"' + expected + "\"", "'" + expected + "'"):
        raise ValueError('unsupported YAML scalar format')
    updated = raw.replace(expected, replacement)
    return source[:node.start_mark.index] + updated + source[node.end_mark.index:]


def apply(plan):
    if plan.get('compatibility') != 'unverified' or not isinstance(plan.get('updates'), list):
        raise ValueError('invalid discovery plan')
    source = VALUES.read_text()
    seen = set()
    for update in plan['updates']:
        key, repo, old, new = (update[x] for x in ('key', 'repository', 'old', 'new'))
        if key in seen or COMPONENTS.get(key) != repo:
            raise ValueError('invalid or repeated component')
        seen.add(key)
        old_version, new_version = version(old), version(new)
        if not old_version or not new_version or new_version <= old_version or old_version[:2] != new_version[:2]:
            raise ValueError('invalid version transition')
        if update.get('release') != f'https://github.com/kubescape/{repo}/releases/tag/{new}':
            raise ValueError('unexpected release URL')
        root = mapping(yaml.compose(source))
        image = mapping(mapping(root[key])['image'])
        if image['repository'].value != f'quay.io/kubescape/{repo}':
            raise ValueError('unexpected image repository')
        source = replace_scalar(source, image['tag'], old, new)
    VALUES.write_text(source)
    operator = next((u for u in plan['updates'] if u['key'] == 'operator'), None)
    if operator:
        source = TEST.read_text()
        old = 'quay.io/kubescape/operator:' + operator['old']
        new = 'quay.io/kubescape/operator:' + operator['new']
        # This is a single, dedicated assertion. Reject drift rather than replacing broadly.
        if source.count(old) != 1:
            raise ValueError('operator test assertion changed')
        TEST.write_text(source.replace(old, new, 1))


if __name__ == '__main__':
    try:
        apply(json.loads(Path(sys.argv[1]).read_text()))
    except (OSError, ValueError, KeyError, IndexError, yaml.YAMLError) as exc:
        sys.exit(f'candidate preparation failed: {exc}')
