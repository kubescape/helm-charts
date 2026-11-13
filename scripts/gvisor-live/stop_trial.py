#!/usr/bin/env python3
"""Live Helm check of gVisor stop observations and source health reports.

Run as root on the prepared disposable K3s node after installing the chart with
stop observations enabled. Phase A runs terminating workloads and controls.
Phase B upgrades the release with stopObservations=false, which also restarts
node-agent so the phase A instance submits its final health report, and checks
that starts still export but stops do not.

Only allowlisted runtime metadata is retained. Raw Pod/CRI errors and agent
logs can contain argv/cwd and are never written to the evidence directory. The
collector checks its full incoming OTLP request for the canary before filtering.
"""
import argparse
import collections
import concurrent.futures
import json
import pathlib
import socket
import subprocess
import time

CANARY = 'GVS_HELM_STOP_CANARY_2026'
IMAGE = 'docker.io/library/busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662'
NS = 'gvisor-helm-20261113'
K = ['k3s', 'kubectl', '--request-timeout=15s']
GVISOR = 'io.containerd.runsc.v1'

# name: (command, how the trial ends it, expected CRI exit code, namespace suffix, ordinary runtime)
PHASE_A = {
    'stop-normal': ('sleep 1; (sleep 1); wait; sleep 2; exit 7', None, 7, '', False),
    'stop-short': ('exit 5', None, 5, '', False),
    'stop-term': ('sleep 600', 'term', 143, '', False),
    'stop-kill': ('sleep 600', 'kill', 137, '', False),
    'stop-exec': ('sleep 600', 'exec', 137, '', False),
    'stop-parallel-a': ('sleep 3; exit 21', None, 21, '', False),
    'stop-parallel-b': ('sleep 3; exit 22', None, 22, '', False),
    'stop-excluded': ('sleep 1; exit 5', None, 5, '-excluded', False),
    'stop-ordinary': ('sleep 1; exit 6', None, 6, '', True),
}
PHASE_B = {'stops-disabled': ('sleep 1; exit 9', None, 9, '', False)}
COUNTERS = [
    'accepted_connections', 'rejected_connections', 'closed_connections', 'handshakes', 'handshake_errors',
    'received_frames', 'read_errors', 'interrupted_reads', 'invalid_frames', 'unresolved_starts',
    'ignored_frames', 'verified_starts', 'callbacks_completed', 'sender_drop_frames', 'queue_drops',
    'canceled_starts', 'recheck_rejected', 'export_submitted', 'listener_failures', 'verified_stops',
    'duplicate_terminals', 'nonterminal_exits', 'unobserved_terminations', 'stop_key_missing',
    'stop_tracking_overflow', 'stop_queue_drops', 'canceled_stops', 'stop_callbacks_completed',
    'stop_recheck_rejected', 'stop_export_submitted']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(args, payload=None, timeout=30):
    result = subprocess.run(args, input=json.dumps(payload) if payload else None,
                            capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, 'experiment command failed (raw error suppressed)')
    return result.stdout


def query(args, payload=None):
    return json.loads(run(args, payload))


def readiness(path, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
                client.settimeout(3)
                client.connect(path)
                client.sendall(b'\x08\x01')
                if client.recv(32) == b'\x08\x01':
                    return
        except OSError:
            pass
        time.sleep(1)
    raise ValueError('trace receiver did not complete the version-1 handshake')


def cri_status(cid):
    return query(['k3s', 'crictl', 'inspect', cid])['status']


def run_pod(name, spec_row):
    command, action, expected, suffix, ordinary = spec_row
    namespace = NS + suffix
    spec = {'restartPolicy': 'Never', 'terminationGracePeriodSeconds': 2, 'containers': [{
        'name': 'workload', 'image': IMAGE, 'imagePullPolicy': 'IfNotPresent',
        'command': ['/bin/sh', '-c', command, CANARY], 'workingDir': '/' + CANARY,
        'volumeMounts': [{'name': 'private-cwd', 'mountPath': '/' + CANARY}],
        'resources': {'limits': {'cpu': '250m', 'memory': '128Mi'}}}],
        'volumes': [{'name': 'private-cwd', 'emptyDir': {}}]}
    if not ordinary:
        spec['runtimeClassName'] = 'gvisor'
    query(K + ['create', '-f', '-', '-o', 'json'], {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        'name': name, 'namespace': namespace, 'labels': {'experiment': NS}}, 'spec': spec})
    end = time.monotonic() + 90
    cid = None
    while time.monotonic() < end:
        pod = query(K + ['get', 'pod', name, '-n', namespace, '-o', 'json'])
        statuses = pod.get('status', {}).get('containerStatuses', [])
        if statuses and statuses[0].get('containerID'):
            cid = statuses[0]['containerID'].split('://', 1)[1]
            if action is None or cri_status(cid)['state'] == 'CONTAINER_RUNNING':
                break
        time.sleep(.2)
    require(cid is not None, 'container did not start')
    extra = {}
    if action == 'term':
        run(['k3s', 'crictl', 'stop', '--timeout', '10', cid], timeout=40)
    elif action == 'kill':
        run(['k3s', 'ctr', '-n', 'k8s.io', 'tasks', 'kill', '--signal', 'SIGKILL', cid])
    elif action == 'exec':
        result = subprocess.run(K + ['exec', '-n', namespace, name, '-c', 'workload', '--', '/bin/sh', '-c',
                                     'sleep 1; exit 4', CANARY], capture_output=True, timeout=30)
        require(result.returncode == 4, 'exec session did not report its own exit code')
        time.sleep(2)
        extra['running_after_exec_exit'] = cri_status(cid)['state'] == 'CONTAINER_RUNNING'
        require(extra['running_after_exec_exit'], 'exec exit stopped the container')
        run(['k3s', 'ctr', '-n', 'k8s.io', 'tasks', 'kill', '--signal', 'SIGKILL', cid])
    while time.monotonic() < end:
        status = cri_status(cid)
        if status['state'] == 'CONTAINER_EXITED':
            break
        time.sleep(.2)
    require(status['state'] == 'CONTAINER_EXITED' and status['exitCode'] == expected, 'unexpected CRI exit')
    containers = query(['k3s', 'crictl', 'ps', '-a', '--id', cid, '-o', 'json'])['containers']
    require(len(containers) == 1 and containers[0]['id'] == cid, 'CRI ID mismatch')
    info = query(['k3s', 'ctr', '-n', 'k8s.io', 'containers', 'info', cid])
    row = {'name': name, 'namespace': namespace, 'pod_uid': pod['metadata']['uid'], 'node': pod['spec']['nodeName'],
           'container_id': cid, 'sandbox_id': containers[0]['podSandboxId'], 'runtime': info['Runtime']['Name'],
           'exit_code': status['exitCode'], 'started_at': status['startedAt'], 'finished_at': status['finishedAt']}
    row.update(extra)
    return row


def run_phase(plan):
    rows = []
    for name, spec_row in plan.items():
        if name.endswith('-parallel-a'):
            continue
        if name.endswith('-parallel-b'):
            pair = [name.replace('-b', '-a'), name]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                rows += list(pool.map(lambda n: run_pod(n, plan[n]), pair))
        else:
            rows.append(run_pod(name, spec_row))
    return rows


def health_ok(h):
    """The documented accounting equations of the final snapshot."""
    return (h['verified_starts'] == h['queue_drops'] + h['canceled_starts'] + h['callbacks_completed']
            and h['callbacks_completed'] == h['recheck_rejected'] + h['export_submitted']
            and h['verified_stops'] == h['stop_queue_drops'] + h['canceled_stops'] + h['stop_callbacks_completed']
            and h['stop_callbacks_completed'] == h['stop_recheck_rejected'] + h['stop_export_submitted'])


def verify(rows_a, rows_b, records, logs, upgrade_ns, config_b):
    require(CANARY not in json.dumps(records) and CANARY not in logs, 'privacy marker retained')
    require(not any(r.get('body') == 'CapturePrivacyFailure' for r in records), 'canary reached the collector')
    for r in records:
        require(r.get('wire_canary_found') is False and r.get('unexpected_attribute_count') == 0, 'wire privacy failure')
    rows = rows_a + rows_b
    require(len({r['container_id'] for r in rows}) == len(rows), 'duplicate container identity')
    traced = {r['container_id']: r for r in rows if r['namespace'] == NS and r['runtime'] == GVISOR}
    traced_a = {cid: r for cid, r in traced.items() if r in rows_a}
    require(len(traced_a) == 7 and len(traced) == 8, 'incomplete runtime ledger')
    obs = [r for r in records if r.get('body') == 'RuntimeObservation']
    starts = collections.Counter(e['container.id'] for e in obs if e.get('kind') == 'container_started')
    stops = [e for e in obs if e.get('kind') == 'container_stopped']
    require(set(starts) == set(traced) and all(n == 1 for n in starts.values()), 'missing, extra or duplicate starts')
    require(sorted(e['container.id'] for e in stops) == sorted(traced_a), 'missing, extra or duplicate stops')
    for e in obs:
        r = traced[e['container.id']]
        require(e.get('source') == 'gvisor_trace' and e.get('identity_status') == 'verified'
                and e.get('identity_origin') == 'local_cri_and_kubernetes', 'wrong observation contract')
        require(all(e.get(k) == r[v] for k, v in [
            ('container.id', 'container_id'), ('sandbox_id', 'sandbox_id'), ('pod_uid', 'pod_uid'),
            ('pod_name', 'name'), ('namespace', 'namespace'), ('node', 'node')]), 'runtime/Pod attribution mismatch')
        require(e.get('container_name') == 'workload' and e.get('runtime_handler') == 'runsc', 'wrong container')
        require(e.get('sender_reported_drops') == 0, 'sender loss reported')
    for e in stops:
        r = traced[e['container.id']]
        signal = r['exit_code'] - 128 if r['exit_code'] > 128 else 0
        require(e.get('exit_code') == r['exit_code'] and e.get('signal') == signal and
                e.get('termination') == ('signaled' if signal else 'exited'), 'stop does not match CRI exit')
        require(e['observed_time_unix_nano'] >= next(s['observed_time_unix_nano'] for s in obs
                if s['container.id'] == e['container.id'] and s['kind'] == 'container_started'), 'stop before start')
    health = [r for r in records if r.get('body') == 'RuntimeSourceHealth']
    require(all(h.get('source') == 'gvisor_trace' for h in health), 'wrong health source')
    require(all(set(COUNTERS) <= set(h) for h in health), 'health report missing counters')
    final = [h for h in health if h['state'] == 'stopped' and h['observed_time_unix_nano'] >= upgrade_ns]
    require(final, 'phase A instance did not submit a final health report')
    a = final[0]
    require(health_ok(a), 'health accounting equations do not hold')
    expected = {'verified_starts': 7, 'export_submitted': 7, 'verified_stops': 7, 'stop_export_submitted': 7,
                'duplicate_terminals': 7, 'unobserved_terminations': 0, 'stop_key_missing': 0,
                'stop_tracking_overflow': 0, 'queue_drops': 0, 'stop_queue_drops': 0, 'listener_failures': 0,
                'invalid_frames': 0, 'handshake_errors': 0, 'rejected_connections': 0}
    for key, value in expected.items():
        require(a[key] == value, 'unexpected final health counter ' + key)
    require(a['nonterminal_exits'] > 0, 'no nonterminal exits were counted')
    periodic = [h for h in health if h['state'] in ('listening', 'connected') and h['observed_time_unix_nano'] < upgrade_ns]
    require(periodic, 'no periodic health report during phase A')
    after = [h for h in health if h['observed_time_unix_nano'] > a['observed_time_unix_nano']
             and h['state'] in ('listening', 'connected')]
    require(after and all(h['verified_stops'] == 0 and h['stop_export_submitted'] == 0 for h in after),
            'stop counters moved with stops disabled')
    require('"stopObservations"' not in config_b and '"gVisorStart"' in config_b, 'phase B config not as expected')
    parallel = [r for r in rows_a if r['name'].startswith('stop-parallel-')]
    overlap = max(r['started_at'] for r in parallel) < min(r['finished_at'] for r in parallel)
    require(overlap, 'parallel workloads did not overlap')
    exec_row = next(r for r in rows_a if r['name'] == 'stop-exec')
    return {
        'phase_a_traced_containers': 7, 'phase_a_starts': 7, 'phase_a_stops': 7,
        'stops_matching_cri_exit_code': len(stops),
        'stop_exit_codes': sorted(e['exit_code'] for e in stops),
        'exec_exit_left_container_running': exec_row['running_after_exec_exit'],
        'excluded_and_ordinary_exports': 0, 'parallel_overlap': overlap,
        'phase_a_periodic_health_reports': len(periodic),
        'phase_a_final_health': {k: a[k] for k in COUNTERS},
        'phase_a_health_equations_hold': True,
        'phase_b_starts': 1, 'phase_b_stops': 0, 'phase_b_health_reports': len(after),
        'phase_b_config_has_stop_observations': False,
        'wire_privacy_checked_before_filtering': True, 'literal_canary_in_agent_logs': False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--observations', required=True)
    parser.add_argument('--chart', required=True)
    parser.add_argument('--values', required=True)
    parser.add_argument('--socket', default='/run/kubescape/gvisor/events.sock')
    args = parser.parse_args()
    out = pathlib.Path(args.output)
    out.mkdir(mode=0o700, exist_ok=False)
    readiness(args.socket)
    for ns in [NS, NS + '-excluded']:
        query(K + ['create', 'namespace', ns, '-o', 'json'])
    rows_a = run_phase(PHASE_A)
    (out / 'runtime-ledger.json').write_text(json.dumps(rows_a, indent=2) + '\n')
    # Let at least one periodic (30 s) health report cover phase A.
    time.sleep(40)
    logs = run(K + ['logs', '-n', 'kubescape', 'daemonset/node-agent', '-c', 'node-agent', '--since=15m'])
    upgrade_ns = time.time_ns()
    run(['helm', 'upgrade', 'kubescape', args.chart, '-n', 'kubescape', '--kubeconfig', '/etc/rancher/k3s/k3s.yaml',
         '-f', args.values, '--set', 'nodeAgent.gVisorStart.stopObservations=false', '--wait', '--timeout', '300s'],
        timeout=330)
    run(K + ['rollout', 'status', 'daemonset/node-agent', '-n', 'kubescape', '--timeout=180s'], timeout=200)
    config_b = query(K + ['get', 'configmap', 'node-agent', '-n', 'kubescape', '-o', 'json'])['data']['config.json']
    readiness(args.socket)
    rows_b = run_phase(PHASE_B)
    (out / 'runtime-ledger.json').write_text(json.dumps(rows_a + rows_b, indent=2) + '\n')
    time.sleep(40)
    logs += run(K + ['logs', '-n', 'kubescape', 'daemonset/node-agent', '-c', 'node-agent', '--since=15m'])
    raw = pathlib.Path(args.observations).read_text()
    records = [json.loads(line) for line in raw.splitlines()]
    result = verify(rows_a, rows_b, records, logs, upgrade_ns, config_b)
    (out / 'observations.jsonl').write_text(raw)
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
