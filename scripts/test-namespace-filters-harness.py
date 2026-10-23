"""Offline fault-injection regressions for the live acceptance harness."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('live', Path(__file__).parent / 'namespace-filters-live/run.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class HarnessTests(unittest.TestCase):
    def harness(self):
        h = object.__new__(live.Acceptance)
        h.args = SimpleNamespace(convergence=1, observation=1)
        return h

    def test_observation_failure_is_not_retried(self):
        h = self.harness()
        h.dispatch_probe = Mock(side_effect=[None, AssertionError('excluded dispatch'), None])
        with self.assertRaisesRegex(AssertionError, 'excluded dispatch'):
            h.observe_dispatch(['filter-a'], ['filter-b'])
        self.assertEqual(h.dispatch_probe.call_count, 2)

    def test_dispatch_negative_assertion_is_fatal_after_convergence(self):
        h = self.harness()
        h.apply = Mock()
        h.kubectl = Mock()
        h.events = Mock(return_value=[{'kind': 'http', 'time': 2, 'value': {
            'path': '/v1/scanImage', 'body': 'namespace-filter-b/deployment-dispatch-42'}}])
        with patch.object(live.time, 'time_ns', return_value=42), patch.object(live.time, 'time', return_value=1):
            with self.assertRaisesRegex(AssertionError, 'excluded workload'):
                h.dispatch_probe(['filter-a'], ['filter-b'])
        self.assertEqual(h.events.call_count, 1)
        self.assertEqual(h.kubectl.call_count, 2)

    def test_deletion_rejects_unrestricted_fallback(self):
        h = self.harness()
        h.filters = Mock()
        h.kubectl = Mock()
        def behavior(allowed, excluded, label):
            self.assertEqual(allowed, ['filter-a'])
            self.assertEqual(excluded, ['filter-b'])
            if label == 'external-deletion-last-valid':
                observed = {'filter-a', 'filter-b'}
                assert not observed.intersection(excluded), 'unrestricted fallback'
        h.behavior = Mock(side_effect=behavior)
        with self.assertRaisesRegex(AssertionError, 'unrestricted fallback'):
            h.deletion_retention()
        h.filters.assert_called_once_with(['filter-a'], name=live.EXTERNAL)
        self.assertEqual(h.behavior.call_count, 2)

    def test_helm4_rejected_before_cluster_operations(self):
        h = self.harness()
        h.command = Mock(return_value='v4.0.0')
        with self.assertRaisesRegex(RuntimeError, 'requires Helm 3'):
            h.setup()
        h.command.assert_called_once_with('helm', 'version', '--short')


if __name__ == '__main__':
    unittest.main()
