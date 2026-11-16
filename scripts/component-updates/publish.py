#!/usr/bin/env python3
"""Publish a validated candidate using only the reserved automation branch."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BRANCH = 'codex/component-image-updates'
MARKER = '<!-- component-updates:v1'
BOT = 'github-actions[bot]'
ALLOWED = {'charts/kubescape-operator/values.yaml',
           'charts/kubescape-operator/tests/operator_image_tag_test.yaml',
           'charts/kubescape-operator/tests/__snapshot__/snapshot_test.yaml.snap'}
REPO = 'kubescape/helm-charts'


def run(*args, input=None, env=None):
    return subprocess.run(args, input=input, text=True, check=True, capture_output=True, env=env).stdout.strip()


def api(path, method='GET', data=None):
    args = ['gh', 'api', '--method', method, path]
    if data is not None:
        args += ['--input', '-']
    output = run(*args, input=json.dumps(data) if data is not None else None)
    return json.loads(output) if output else None


def pages(path):
    result = []
    for page in range(1, 101):
        separator = '&' if '?' in path else '?'
        items = api(f'{path}{separator}per_page=100&page={page}')
        if not isinstance(items, list):
            raise ValueError('unexpected paginated response')
        result.extend(items)
        if len(items) < 100:
            return result
    raise ValueError('pagination limit exceeded')


def human(item):
    user = item.get('user') or item.get('actor') or {}
    return user.get('type') != 'Bot' and user.get('login') != BOT


def ensure_unadopted(pr, head):
    base = pr.get('base') or {}
    if base.get('ref') != 'main' or (base.get('repo') or {}).get('full_name') != REPO:
        raise ValueError('draft base changed; refusing update')
    if pr['user']['login'] != BOT or not pr['draft'] or pr['head']['sha'] != head:
        raise ValueError('draft ownership or head changed; refusing update')
    match = re.search(r'\n<!-- component-updates:v1 head=([0-9a-f]{40}) body=([0-9a-f]{64}) -->\s*$', pr.get('body') or '')
    if not match or match.group(1) != head:
        raise ValueError('draft marker or recorded head does not match')
    body = pr['body'][:match.start()]
    if hashlib.sha256(body.encode()).hexdigest() != match.group(2):
        raise ValueError('draft description was edited by a human')
    prefix = f'repos/{REPO}/pulls/{pr["number"]}'
    for endpoint in ('reviews', 'comments', 'commits'):
        for item in pages(f'{prefix}/{endpoint}'):
            if endpoint == 'commits':
                if (item.get('author') or {}).get('login') != BOT:
                    raise ValueError('human or unknown commit on draft')
            elif human(item):
                raise ValueError('human review activity on draft')
    for item in pages(f'repos/{REPO}/issues/{pr["number"]}/timeline'):
        if item.get('event') in ('ready_for_review', 'converted_to_draft') and human(item):
            raise ValueError('human changed draft readiness')


def body_for(plan, run_url):
    rows = ['## Component image candidates', '', '| Component | Current | Proposed |', '| --- | --- | --- |']
    for item in plan['updates']:
        rows.append(f"| {item['repository']} | {item['old']} | [{item['new']}]({item['release']}) |")
    rows += ['', '**Compatibility is unverified.** Review schema, protocol, and API authentication changes together before merging.',
             '', 'Helm lint and the pinned Helm unit suite passed before this proposal was created.',
             f'Validation run: {run_url}', '', 'Skipped or manual-review items:']
    rows.extend('- ' + item for item in plan['skipped'])
    if not plan['skipped']:
        rows.append('- None')
    rows += ['', 'Regular pull request checks may require maintainer approval before running.']
    return '\n'.join(rows)


def publish(plan_path, base):
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('publication is restricted to upstream main')
    plan = json.loads(Path(plan_path).read_text())
    if not plan['updates']:
        print('No updates; nothing to publish.')
        return
    current = api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
    if current != base or run('git', 'rev-parse', 'HEAD') != base:
        raise ValueError('main changed since candidate validation')
    changed = set(run('git', 'diff', '--name-only').splitlines())
    if not changed or not changed <= ALLOWED:
        raise ValueError('candidate modifies unexpected files')
    prs = pages(f'repos/{REPO}/pulls?state=open&head=kubescape:{BRANCH}')
    if len(prs) > 1:
        raise ValueError('multiple open automation PRs')
    refs = api(f'repos/{REPO}/git/matching-refs/heads/{BRANCH}')
    exact = [r for r in refs if r['ref'] == 'refs/heads/' + BRANCH]
    if len(exact) > 1:
        raise ValueError('ambiguous branch')
    head = exact[0]['object']['sha'] if exact else None
    pr = prs[0] if prs else None
    orphan = False
    if pr:
        if not head:
            raise ValueError('PR branch is missing')
        ensure_unadopted(pr, head)
    elif head:
        closed = pages(f'repos/{REPO}/pulls?state=closed&head=kubescape:{BRANCH}')
        previous = next((item for item in closed if item['head']['sha'] == head), None)
        marker = re.search(r'\n<!-- component-updates:v1 head=([0-9a-f]{40}) body=([0-9a-f]{64}) -->\s*$', (previous or {}).get('body') or '')
        if not closed:
            orphan = True
        elif (not previous or not previous.get('merged_at') or previous['user']['login'] != BOT or
                not marker or marker.group(1) != head or
                hashlib.sha256(previous['body'][:marker.start()].encode()).hexdigest() != marker.group(2)):
            raise ValueError('reserved branch exists without an open or merged owned PR; manual recovery required')
    run('git', 'add', '--', *sorted(changed))
    tree = run('git', 'write-tree')
    if head:
        run('git', 'fetch', '--no-tags', 'origin', f'+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}')
        if run('git', 'rev-parse', f'refs/remotes/origin/{BRANCH}') != head:
            raise ValueError('branch changed during fetch')
        if orphan:
            commit_info = api(f'repos/{REPO}/commits/{head}')
            if ((commit_info.get('author') or {}).get('login') != BOT or
                    run('git', 'rev-parse', f'{head}^') != base or
                    len(commit_info.get('parents', [])) != 1 or
                    run('git', 'rev-parse', f'{head}^{{tree}}') != tree or
                    'Signed-off-by: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>' not in commit_info['commit']['message']):
                raise ValueError('orphaned branch ownership or content cannot be proven')
            run_url = f"{os.environ['GITHUB_SERVER_URL']}/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            body = body_for(plan, run_url)
            body += f'\n<!-- component-updates:v1 head={head} body={hashlib.sha256(body.encode()).hexdigest()} -->'
            api(f'repos/{REPO}/pulls', 'POST', {'title': 'chore: propose grouped component image updates',
                'head': BRANCH, 'base': 'main', 'body': body, 'draft': True})
            print('Recovered draft candidate from owned branch.')
            return
        if run('git', 'rev-parse', f'{head}^{{tree}}') == tree:
            print('Candidate is unchanged.')
            return
        if pr:
            ensure_unadopted(api(f'repos/{REPO}/pulls/{pr["number"]}'), head)
    if api(f'repos/{REPO}/git/ref/heads/main')['object']['sha'] != base:
        raise ValueError('main changed before publication')
    env = os.environ.copy()
    env.update({'GIT_AUTHOR_NAME': BOT, 'GIT_AUTHOR_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com',
                'GIT_COMMITTER_NAME': BOT, 'GIT_COMMITTER_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com'})
    parents = ['-p', head, '-p', base] if head and head != base else ['-p', base]
    message = 'chore: update component image candidates\n\nSigned-off-by: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>\n'
    commit = run('git', 'commit-tree', tree, *parents, input=message, env=env)
    token = os.environ['GH_TOKEN']
    env.update({'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
                'GIT_CONFIG_VALUE_0': 'AUTHORIZATION: basic ' + base64.b64encode(('x-access-token:' + token).encode()).decode()})
    run('git', 'push', 'origin', f'{commit}:refs/heads/{BRANCH}', env=env)
    run_url = f"{os.environ['GITHUB_SERVER_URL']}/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    body = body_for(plan, run_url)
    body += f'\n<!-- component-updates:v1 head={commit} body={hashlib.sha256(body.encode()).hexdigest()} -->'
    if pr:
        api(f'repos/{REPO}/pulls/{pr["number"]}', 'PATCH', {'body': body})
    else:
        api(f'repos/{REPO}/pulls', 'POST', {'title': 'chore: propose grouped component image updates',
            'head': BRANCH, 'base': 'main', 'body': body, 'draft': True})
    print('Published draft candidate.')


if __name__ == '__main__':
    try:
        publish(sys.argv[1], sys.argv[2])
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f'publication stopped: {exc}')
