#!/usr/bin/env python3
"""Run on the prepared disposable K3s node after installing the chart.

Only allowlisted runtime metadata is retained. Raw Pod/CRI errors and agent
logs can contain argv/cwd and must never be written to the evidence directory.
The separate collector must check its full incoming OTLP request before filtering.
"""
import argparse
import collections
import concurrent.futures
from datetime import datetime
import json
import pathlib
import socket
import struct
import subprocess
import time

CANARY = 'GVS_INTEGRATION_CANARY_2026'
IMAGE = 'docker.io/library/busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662'
NS = 'gvisor-helm-20261106'
K = ['k3s', 'kubectl', '--request-timeout=15s']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def query(args, payload=None):
    result = subprocess.run(args, input=json.dumps(payload) if payload else None,
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'experiment query failed (raw error suppressed)')
    return json.loads(result.stdout)


def readiness(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
        client.settimeout(3)
        client.connect(path)
        client.sendall(b'\x08\x01')
        require(client.recv(32) == b'\x08\x01', 'unexpected trace handshake')


def run_pod(name, namespace=NS, ordinary=False):
    spec = {'restartPolicy': 'Never', 'containers': [{
        'name': 'workload', 'image': IMAGE, 'imagePullPolicy': 'IfNotPresent',
        'command': ['/bin/sh', '-c', 'sleep 4', CANARY],
        'workingDir': '/' + CANARY,
        'volumeMounts': [{'name': 'private-cwd', 'mountPath': '/' + CANARY}],
        'resources': {'limits': {'cpu': '500m', 'memory': '256Mi'}}}],
        'volumes': [{'name': 'private-cwd', 'emptyDir': {}}]}
    if not ordinary:
        spec['runtimeClassName'] = 'gvisor'
    query(K + ['create', '-f', '-', '-o', 'json'], {
        'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
            'name': name, 'namespace': namespace,
            'labels': {'experiment': 'gvisor-helm-20261106'}}, 'spec': spec})
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        pod = query(K + ['get', 'pod', name, '-n', namespace, '-o', 'json'])
        statuses = pod.get('status', {}).get('containerStatuses', [])
        if statuses and 'terminated' in statuses[0].get('state', {}):
            status = statuses[0]
            end = status['state']['terminated']
            cid = status['containerID'].split('://', 1)[1]
            containers = query(['k3s', 'crictl', 'ps', '-a', '--id', cid, '-o', 'json'])['containers']
            require(len(containers) == 1 and containers[0]['id'] == cid, 'CRI ID mismatch')
            info = query(['k3s', 'ctr', '-n', 'k8s.io', 'containers', 'info', cid])
            require(end['exitCode'] == 0, 'workload did not succeed')
            return {'name': name, 'namespace': namespace, 'pod_uid': pod['metadata']['uid'],
                    'node': pod['spec']['nodeName'], 'container_id': cid,
                    'sandbox_id': containers[0]['podSandboxId'], 'runtime': info['Runtime']['Name'],
                    'exit_code': end['exitCode'], 'started_at': end['startedAt'],
                    'finished_at': end['finishedAt'], 'image_id': status['imageID']}
        time.sleep(.25)
    raise ValueError('workload completion timed out (raw status suppressed)')


def verify(rows, events, logs, count):
    require(CANARY not in json.dumps(events) and CANARY not in logs, 'privacy marker retained')
    require(len(rows) == count+4 and len({r['container_id'] for r in rows}) == len(rows), 'incomplete or duplicate control ledger')
    require(sum(r['runtime'] != 'io.containerd.runsc.v1' for r in rows) == 1
            and sum(r['namespace'] != NS for r in rows) == 1, 'missing ordinary or excluded control')
    require(all(r['exit_code'] == 0 for r in rows), 'failed workload in ledger')
    expected = {r['container_id']: r for r in rows
                if r['namespace'] == NS and r['runtime'] == 'io.containerd.runsc.v1'}
    require(len(expected) == count + 2, 'incomplete runtime ledger')
    counts = collections.Counter(e.get('container.id') for e in events)
    require(set(counts) == set(expected) and all(n == 1 for n in counts.values()),
            'missing, extra or duplicate observations')
    for e in events:
        r = expected[e['container.id']]
        require(e.get('body') == 'RuntimeObservation' and e.get('source') == 'gvisor_trace'
                and e.get('kind') == 'container_started' and e.get('identity_status') == 'verified'
                and e.get('identity_origin') == 'local_cri_and_kubernetes', 'wrong event contract')
        require(all(e.get(k) == r[v] for k, v in [
            ('container.id', 'container_id'), ('sandbox_id', 'sandbox_id'),
            ('pod_uid', 'pod_uid'), ('pod_name', 'name'), ('namespace', 'namespace'), ('node', 'node')]),
            'runtime/Pod attribution mismatch')
        require(e.get('container_name') == 'workload' and e.get('runtime_handler') == 'runsc', 'wrong container')
        require(e.get('sender_reported_drops') == 0 and e.get('wire_canary_found') is False
                and e.get('unexpected_attribute_count') == 0, 'loss or wire privacy failure')
    parallel = [r for r in rows if r['name'].startswith('helm-live-parallel-')]
    stamp = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
    overlap = len(parallel) == 2 and max(stamp(r['started_at']) for r in parallel) < min(stamp(r['finished_at']) for r in parallel)
    require(overlap, 'concurrent workloads did not overlap')
    return {'repeated_expected': count, 'repeated_received': len(events)-2,
            'concurrent_received': 2, 'concurrent_overlap': overlap,
            'ordinary_excluded_unknown_exports': 0, 'identity_matches': len(events),
            'wire_privacy_checked_before_filtering': True, 'literal_canary_in_agent_logs': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--observations', required=True)
    parser.add_argument('--socket', default='/run/kubescape/gvisor/events.sock')
    parser.add_argument('--count', type=int, default=20)
    args = parser.parse_args()
    require(1 <= args.count <= 20, 'count must be 1..20')
    out = pathlib.Path(args.output)
    out.mkdir(mode=0o700, exist_ok=False)
    readiness(args.socket)
    for ns in [NS, NS+'-excluded']:
        query(K+['create', 'namespace', ns, '-o', 'json'])
    rows = []
    for i in range(args.count):
        rows.append(run_pod('helm-live-%02d' % (i+1)))
        (out/'runtime-ledger.json').write_text(json.dumps(rows, indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows += list(pool.map(run_pod, ['helm-live-parallel-a', 'helm-live-parallel-b']))
    rows.append(run_pod('helm-live-excluded', NS+'-excluded'))
    rows.append(run_pod('helm-live-ordinary', ordinary=True))
    unknown = 'e'*64
    require(not query(['k3s','crictl','ps','-a','--id',unknown,'-o','json'])['containers'], 'unknown fixture ID exists')
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
        client.settimeout(3); client.connect(args.socket); client.sendall(b'\x08\x01')
        require(client.recv(32)==b'\x08\x01','unexpected handshake')
        client.sendall(struct.pack('<HHI',8,1,0)+b'\x12\x40'+unknown.encode())
    (out/'runtime-ledger.json').write_text(json.dumps(rows, indent=2)+'\n')
    time.sleep(8)
    raw = pathlib.Path(args.observations).read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    logs = subprocess.run(K+['logs','-n','kubescape','daemonset/node-agent','--since=10m'],capture_output=True,text=True,timeout=30)
    require(logs.returncode == 0, 'cannot scan agent logs')
    result = verify(rows, events, logs.stdout, args.count)
    (out/'observations.jsonl').write_text(raw)
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
