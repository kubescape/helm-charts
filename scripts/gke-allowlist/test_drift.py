"""Offline Helm-to-allowlist regression tests; requires Helm 3.19 and PyYAML."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / 'charts/kubescape-operator'
ALLOWLIST = ROOT / 'gke-allowlist/armo-kubescape-node-agent-1.40-v2.yaml'


def render(*settings):
    command = ['helm', 'template', 'allowlist-test', str(CHART), '--kube-version', '1.33.0',
               '--set', 'clusterName=test', '--set', 'unittest=true']
    for setting in settings:
        command += ['--set', setting]
    return subprocess.run(command, capture_output=True, text=True)


def daemonset(output):
    return next(doc for doc in yaml.safe_load_all(output)
                if doc and doc.get('kind') == 'DaemonSet' and doc['metadata']['name'] == 'node-agent')


class AllowlistDriftTests(unittest.TestCase):
    def test_release_check_covers_supported_autopilot_profiles(self):
        result = subprocess.run([str(ROOT / 'scripts/gke-allowlist/check-drift.sh'), str(CHART), str(ALLOWLIST)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('proxy', result.stdout)
        self.assertIn('sbom-scanner', result.stdout)

    def test_legacy_sidecar_proxy_rejected_in_each_render_path(self):
        for mode in ('nodeAgent.autoscaler.enabled=false', 'nodeAgent.autoscaler.enabled=true',
                     'nodeAgent.multipleDaemonSets.enabled=true'):
            with self.subTest(mode=mode):
                configurations = ('nodeAgent.multipleDaemonSets.configurations[0].resources.limits.memory=1Gi',) if 'multipleDaemonSets' in mode else ()
                result = render('nodeAgent.gke.allowlist.enabled=true', 'nodeAgent.sbomScanner.enabled=true',
                                'global.httpsProxy=http://proxy:3128', mode, *configurations)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('supportsSbomScannerProxy', result.stderr)

    def test_non_gke_sidecar_keeps_proxy(self):
        result = render('nodeAgent.sbomScanner.enabled=true', 'global.httpsProxy=http://proxy:3128')
        self.assertEqual(result.returncode, 0, result.stderr)
        containers = daemonset(result.stdout)['spec']['template']['spec']['containers']
        scanner = next(c for c in containers if c['name'] == 'sbom-scanner')
        self.assertIn('HTTPS_PROXY', {e['name'] for e in scanner['env']})
        self.assertIn('no_proxy', {e['name'] for e in scanner['env']})

    def test_sidecar_proxy_capability_does_not_hide_unapproved_fields(self):
        result = subprocess.run(['python3', str(ROOT / 'scripts/gke-allowlist/allowlist-drift.py'),
                                 '--chart', str(CHART), '--allowlist', str(ALLOWLIST),
                                 '--set', 'nodeAgent.gke.allowlist.enabled=true',
                                 '--set', 'nodeAgent.gke.allowlist.supportsSbomScannerProxy=true',
                                 '--set', 'nodeAgent.sbomScanner.enabled=true',
                                 '--set', 'global.httpsProxy=http://proxy:3128'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("container 'sbom-scanner': env HTTPS_PROXY not in allowlist", result.stdout)
        self.assertIn("container 'sbom-scanner': env no_proxy not in allowlist", result.stdout)

    def test_explicitly_supported_sidecar_proxy_keeps_env(self):
        result = render('nodeAgent.gke.allowlist.enabled=true', 'nodeAgent.gke.allowlist.supportsSbomScannerProxy=true',
                        'nodeAgent.sbomScanner.enabled=true', 'global.httpsProxy=http://proxy:3128')
        self.assertEqual(result.returncode, 0, result.stderr)
        containers = daemonset(result.stdout)['spec']['template']['spec']['containers']
        scanner = next(c for c in containers if c['name'] == 'sbom-scanner')
        self.assertIn('HTTPS_PROXY', {e['name'] for e in scanner['env']})
        self.assertIn('no_proxy', {e['name'] for e in scanner['env']})

    def test_legacy_autopilot_render_uses_api_token_fallback(self):
        result = render('nodeAgent.gke.allowlist.enabled=true')
        self.assertEqual(result.returncode, 0, result.stderr)
        spec = daemonset(result.stdout)['spec']['template']['spec']
        self.assertNotIn('kubescape-api-token', {v['name'] for v in spec['volumes']})

    def test_check_still_detects_missing_approved_proxy_env(self):
        allowlist = yaml.safe_load(ALLOWLIST.read_text())
        agent = next(c for c in allowlist['matchingCriteria']['containers'] if c['name'] == 'node-agent')
        agent['env'] = [e for e in agent['env'] if e['name'] != 'HTTPS_PROXY']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'allowlist.yaml'
            path.write_text(yaml.safe_dump(allowlist))
            result = subprocess.run([str(ROOT / 'scripts/gke-allowlist/check-drift.sh'), str(CHART), str(path)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("container 'node-agent': env HTTPS_PROXY not in allowlist", result.stdout)

    def test_token_capability_override_is_still_checked_against_approval(self):
        result = subprocess.run(['python3', str(ROOT / 'scripts/gke-allowlist/allowlist-drift.py'),
                                 '--chart', str(CHART), '--allowlist', str(ALLOWLIST),
                                 '--set', 'nodeAgent.gke.allowlist.enabled=true',
                                 '--set', 'nodeAgent.gke.allowlist.supportsApiToken=true'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('mountPath /var/run/secrets/kubescape.io/api-token not in allowlist', result.stdout)

    def test_wrapper_uses_prefixed_autopilot_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory)
            (wrapper / 'Chart.yaml').write_text(yaml.safe_dump({
                'apiVersion': 'v2', 'name': 'test-wrapper', 'version': '0.1.0',
                'dependencies': [{'name': 'kubescape-operator', 'version': yaml.safe_load((CHART / 'Chart.yaml').read_text())['version'],
                                  'repository': CHART.as_uri()}]}))
            result = subprocess.run([str(ROOT / 'scripts/gke-allowlist/check-drift.sh'),
                                     str(wrapper), str(ALLOWLIST), '--wrapper'],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_allowlist_is_a_non_acknowledgeable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'allowlist.yaml'
            path.write_text('not-an-allowlist: true\n')
            result = subprocess.run([str(ROOT / 'scripts/gke-allowlist/check-drift.sh'),
                                     str(CHART), str(path)], capture_output=True, text=True)
        self.assertNotIn(result.returncode, (0, 2))


if __name__ == '__main__':
    unittest.main()
