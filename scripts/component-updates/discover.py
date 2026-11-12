#!/usr/bin/env python3
"""Discover chart image candidates; never writes files or creates pull requests."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = {
    'nodeAgent': 'node-agent', 'kubevuln': 'kubevuln', 'storage': 'storage',
    'operator': 'operator', 'kubescape': 'kubescape', 'synchronizer': 'synchronizer',
    'prometheusExporter': 'prometheus-exporter',
}
VERSION = re.compile(r'^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')


def version(tag):
    match = VERSION.fullmatch(tag) if isinstance(tag, str) else None
    return tuple(map(int, match.groups())) if match else None


def request(url, token=None, accept='application/vnd.github+json'):
    headers = {'Accept': accept, 'User-Agent': 'kubescape-component-updates'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response), response.headers


def releases(repo, token):
    url = f'https://api.github.com/repos/kubescape/{repo}/releases?per_page=100'
    result = []
    for _ in range(100):
        data, headers = request(url, token)
        if not isinstance(data, list):
            raise ValueError(f'{repo}: unexpected releases response')
        result.extend(data)
        link = headers.get('Link', '')
        next_links = re.findall(r'<([^>]+)>;\s*rel="next"', link)
        if not next_links:
            return result
        url = next_links[0]
        if not (url.startswith('https://api.github.com/repos/kubescape/' + repo + '/releases?') or
                re.fullmatch(r'https://api\.github\.com/repositories/[0-9]+/releases\?[A-Za-z0-9=&%_-]+', url)):
            raise ValueError('unexpected pagination URL')
    raise ValueError(f'{repo}: pagination limit exceeded')


def verify_image(repo, tag):
    url = f'https://quay.io/v2/kubescape/{repo}/manifests/{tag}'
    manifest, _ = request(url, accept='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json')
    platforms = {(item.get('platform', {}).get('os'), item.get('platform', {}).get('architecture'))
                 for item in manifest.get('manifests', [])}
    if not {('linux', 'amd64'), ('linux', 'arm64')} <= platforms:
        raise ValueError(f'{repo}:{tag}: missing linux/amd64 or linux/arm64 manifest')


def mapping(node):
    if not isinstance(node, yaml.MappingNode):
        raise ValueError('expected YAML mapping')
    out = {}
    for key, value in node.value:
        if key.value in out:
            raise ValueError(f'duplicate YAML key: {key.value}')
        out[key.value] = value
        check_nested(value)
    return out


def check_nested(node):
    if isinstance(node, yaml.MappingNode):
        mapping(node)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            check_nested(item)


def discover(path, token):
    root = mapping(yaml.compose(path.read_text()))
    updates, skipped = [], []
    for key, repo in COMPONENTS.items():
        image = mapping(mapping(root[key])['image'])
        if image['repository'].value != f'quay.io/kubescape/{repo}':
            raise ValueError(f'{key}: unexpected image repository')
        current = image['tag'].value
        current_version = version(current)
        if current_version is None:
            raise ValueError(f'{key}: invalid current version')
        published = releases(repo, token)
        if not published:
            skipped.append(f'{repo}: no published releases')
        stable = [(version(r.get('tag_name')), r.get('tag_name')) for r in published
                  if not r.get('draft') and not r.get('prerelease') and version(r.get('tag_name'))]
        newer = [(v, tag) for v, tag in stable if v > current_version]
        larger = [tag for v, tag in newer if v[:2] != current_version[:2]]
        if larger:
            skipped.append(f'{repo}: newer major/minor releases require manual review: {", ".join(larger)}')
        eligible = [(v, tag) for v, tag in newer if v[:2] == current_version[:2]]
        if eligible:
            _, tag = max(eligible)
            verify_image(repo, tag)
            updates.append({'key': key, 'repository': repo, 'old': current, 'new': tag,
                            'release': f'https://github.com/kubescape/{repo}/releases/tag/{tag}'})
    return {'updates': updates, 'skipped': skipped, 'compatibility': 'unverified'}


def main():
    try:
        print(json.dumps(discover(ROOT / 'charts/kubescape-operator/values.yaml', os.environ.get('GH_TOKEN')), indent=2))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f'discovery failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
