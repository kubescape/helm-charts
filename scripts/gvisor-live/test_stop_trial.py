import copy
import unittest

from stop_trial import CANARY, GVISOR, HEALTH_FIELDS, NS, rfc3339_ns, verify

CODES = {'stop-normal': 7, 'stop-short': 5, 'stop-term': 143, 'stop-kill': 137, 'stop-exec': 137,
         'stop-parallel-a': 21, 'stop-parallel-b': 22}
BASE = rfc3339_ns('2026-11-13T10:00:00Z')
UPGRADE = BASE + 5000


def row(i, name, code, namespace=NS, runtime=GVISOR, finished='2026-11-13T10:00:05Z'):
    return {'name': name, 'namespace': namespace, 'pod_uid': 'uid-%d' % i, 'node': 'node',
            'container_id': ('%x' % i) * 64, 'sandbox_id': 's%d' % i, 'runtime': runtime, 'exit_code': code,
            'started_at': '2026-11-13T10:00:00Z', 'finished_at': finished,
            'running_after_exec_exit': True if name == 'stop-exec' else None}


def observation(r, kind, t):
    e = {'body': 'RuntimeObservation', 'observed_time_unix_nano': t, 'wire_canary_found': False,
         'unexpected_attribute_count': 0, 'source': 'gvisor_trace', 'kind': kind, 'identity_status': 'verified',
         'identity_origin': 'local_cri_and_kubernetes', 'node': r['node'], 'container.id': r['container_id'],
         'sandbox_id': r['sandbox_id'], 'runtime_handler': 'runsc', 'namespace': r['namespace'],
         'pod_name': r['name'], 'pod_uid': r['pod_uid'], 'container_name': 'workload', 'sender_reported_drops': 0}
    if kind == 'container_stopped':
        signal = r['exit_code'] - 128 if r['exit_code'] > 128 else 0
        e.update(exit_code=r['exit_code'], signal=signal, termination='signaled' if signal else 'exited')
    return e


def health(t, state, **values):
    h = {'body': 'RuntimeSourceHealth', 'observed_time_unix_nano': t, 'wire_canary_found': False,
         'unexpected_attribute_count': 0, 'source': 'gvisor_trace', 'state': state}
    h.update({k: 0 for k in HEALTH_FIELDS})
    h.update(values)
    return h


def fixture():
    rows_a = [row(i + 1, name, code) for i, (name, code) in enumerate(CODES.items())]
    rows_a += [row(8, 'stop-excluded', 5, namespace=NS + '-excluded'),
               row(9, 'stop-ordinary', 6, runtime='io.containerd.runc.v2')]
    # Phase B's workload exits 6.5 microseconds after BASE, between its start and its health report.
    rows_b = [row(10, 'stops-disabled', 9, finished='2026-11-13T10:00:00.0000065Z')]
    records = []
    for i, r in enumerate(rows_a[:7]):
        records += [observation(r, 'container_started', BASE + 100 + i),
                    observation(r, 'container_stopped', BASE + 200 + i)]
    records.append(observation(rows_b[0], 'container_started', BASE + 6000))
    final = dict(verified_starts=7, callbacks_completed=7, export_submitted=7, verified_stops=7,
                 stop_callbacks_completed=7, stop_export_submitted=7, duplicate_terminals=7, nonterminal_exits=12)
    records += [health(BASE + 300, 'connected', verified_starts=7), health(UPGRADE + 1, 'stopped', **final),
                health(BASE + 7000, 'connected', verified_starts=1, callbacks_completed=1, export_submitted=1)]
    config_b = '{"gVisorStart": {"enabled": true}}'
    return rows_a, rows_b, records, '', UPGRADE, config_b


class VerifyTests(unittest.TestCase):
    def test_valid_run(self):
        result = verify(*fixture())
        self.assertEqual((result['phase_a_stops'], result['phase_b_stops']), (7, 0))
        self.assertEqual(result['stop_exit_codes'], [5, 7, 21, 22, 137, 137, 143])

    def test_stop_mismatches_fail(self):
        for change in [{'exit_code': 0}, {'signal': 0}, {'termination': 'exited'}, {'pod_uid': 'other'}]:
            rows_a, rows_b, records, logs, upgrade, config = fixture()
            stop = next(r for r in records if r.get('kind') == 'container_stopped' and r['pod_name'] == 'stop-term')
            stop.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(rows_a, rows_b, records, logs, upgrade, config)

    def test_missing_extra_and_disabled_stops_fail(self):
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        stops = [r for r in records if r.get('kind') == 'container_stopped']
        disabled_stop = observation(rows_b[0], 'container_stopped', BASE + 6100)
        excluded_stop = observation(rows_a[7], 'container_stopped', BASE + 250)
        for bad in [[r for r in records if r is not stops[0]], records + [stops[0]],
                    records + [disabled_stop], records + [excluded_stop]]:
            with self.subTest(length=len(bad)), self.assertRaises((ValueError, KeyError)):
                verify(rows_a, rows_b, bad, logs, upgrade, config)

    def test_health_accounting_fails_closed(self):
        for change in [{'stop_export_submitted': 6}, {'unobserved_terminations': 1}, {'verified_stops': 8},
                       {'state': 'connected'}, {'nonterminal_exits': 0},
                       {'sender_drop_frames': 1}, {'read_errors': 1}]:
            rows_a, rows_b, records, logs, upgrade, config = fixture()
            final = next(r for r in records if r.get('state') == 'stopped')
            final.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(rows_a, rows_b, records, logs, upgrade, config)
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        records[-1]['verified_stops'] = 1
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, logs, upgrade, config)

    def test_health_shape_requires_active_connections(self):
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        del records[-1]['active_connections']
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, logs, upgrade, config)

    def test_phase_b_report_must_follow_workload_exit(self):
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        rows_b[0]['finished_at'] = '2026-11-13T10:00:00.0000075Z'
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, logs, upgrade, config)
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        records[-1]['verified_starts'] = 0
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, logs, upgrade, config)

    def test_timestamp_parsing(self):
        self.assertEqual(rfc3339_ns('2026-11-13T22:26:24.86570655+05:30') - rfc3339_ns('2026-11-13T16:56:24Z'),
                         865706550)

    def test_privacy_and_config_fail_closed(self):
        rows_a, rows_b, records, logs, upgrade, config = fixture()
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, CANARY, upgrade, config)
        bad = copy.deepcopy(records)
        bad[0]['wire_canary_found'] = True
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, bad, logs, upgrade, config)
        with self.assertRaises(ValueError):
            verify(rows_a, rows_b, records, logs, upgrade, '{"gVisorStart": {"stopObservations": true}}')


if __name__ == '__main__':
    unittest.main()
