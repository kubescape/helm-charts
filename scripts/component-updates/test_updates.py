import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
import discover
import prepare
import publish


class DiscoveryTests(unittest.TestCase):
    def test_versions(self):
        self.assertGreater(discover.version('v0.3.10'), discover.version('0.3.9'))
        for value in ('latest', 'v1.2.3-rc1', 'v01.2.3', None):
            self.assertIsNone(discover.version(value))

    def test_numeric_repository_pagination(self):
        responses = [([{'tag_name': 'v1.0.1'}], {'Link': '<https://api.github.com/repositories/123/releases?per_page=100&page=2>; rel="next"'}),
                     ([{'tag_name': 'v1.0.2'}], {})]
        with patch.object(discover, 'request', side_effect=responses):
            self.assertEqual(len(discover.releases('storage', 'token')), 2)

    def test_untrusted_pagination_is_rejected(self):
        with patch.object(discover, 'request', return_value=([], {'Link': '<https://evil.test/releases>; rel="next"'})):
            with self.assertRaises(ValueError):
                discover.releases('storage', 'secret')

    def test_manifest_requires_both_architectures(self):
        with patch.object(discover, 'request', return_value=({'manifests': [{'platform': {'os': 'linux', 'architecture': 'amd64'}}]}, {})):
            with self.assertRaises(ValueError):
                discover.verify_image('storage', 'v0.0.1')

    def test_duplicate_yaml_key(self):
        with self.assertRaises(ValueError):
            discover.mapping(yaml.compose('a: 1\na: 2\n'))

    def test_grouped_patch_selection(self):
        data = {key: {'image': {'repository': 'quay.io/kubescape/' + repo, 'tag': 'v0.3.9'}} for key, repo in discover.COMPONENTS.items()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'values.yaml'
            path.write_text(yaml.safe_dump(data))
            releases = [{'tag_name': 'v0.3.10', 'draft': False, 'prerelease': False},
                        {'tag_name': 'v0.4.0', 'draft': False, 'prerelease': False},
                        {'tag_name': 'v0.3.99', 'draft': True, 'prerelease': False},
                        {'tag_name': 'v0.3.100-rc1', 'draft': False, 'prerelease': True}]
            with patch.object(discover, 'releases', return_value=releases), patch.object(discover, 'verify_image'):
                plan = discover.discover(path, None)
        self.assertEqual(len(plan['updates']), 7)
        self.assertTrue(all(item['new'] == 'v0.3.10' for item in plan['updates']))
        self.assertEqual(len(plan['skipped']), 7)

    def test_empty_and_api_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'values.yaml'
            path.write_text(yaml.safe_dump({key: {'image': {'repository': 'quay.io/kubescape/' + repo, 'tag': 'v0.3.9'}} for key, repo in discover.COMPONENTS.items()}))
            with patch.object(discover, 'releases', return_value=[]):
                self.assertEqual(len(discover.discover(path, None)['skipped']), 7)
            with patch.object(discover, 'releases', side_effect=OSError('rate limited')):
                with self.assertRaises(OSError):
                    discover.discover(path, None)


class PrepareTests(unittest.TestCase):
    def test_scalar_preserves_comments_and_quotes(self):
        source = 'image:\n  tag: "v0.1.2" # keep\n'
        node = discover.mapping(discover.mapping(yaml.compose(source))['image'])['tag']
        self.assertEqual(prepare.replace_scalar(source, node, 'v0.1.2', 'v0.1.3'), 'image:\n  tag: "v0.1.3" # keep\n')
        with self.assertRaises(ValueError):
            prepare.replace_scalar(source, node, 'v0.1.1', 'v0.1.3')

    def test_apply_two_updates_changes_only_target_scalars(self):
        with tempfile.TemporaryDirectory() as directory:
            values = Path(directory) / 'values.yaml'
            test = Path(directory) / 'operator.yaml'
            original = '# keep\nstorage:\n  image:\n    repository: quay.io/kubescape/storage\n    tag: v0.0.1 # keep\noperator:\n  image:\n    repository: quay.io/kubescape/operator\n    tag: v0.2.1\nother: untouched\n'
            values.write_text(original)
            test.write_text('value: quay.io/kubescape/operator:v0.2.1\n')
            plan = {'compatibility': 'unverified', 'updates': [
                {'key': 'storage', 'repository': 'storage', 'old': 'v0.0.1', 'new': 'v0.0.2', 'release': 'https://github.com/kubescape/storage/releases/tag/v0.0.2'},
                {'key': 'operator', 'repository': 'operator', 'old': 'v0.2.1', 'new': 'v0.2.2', 'release': 'https://github.com/kubescape/operator/releases/tag/v0.2.2'}]}
            with patch.object(prepare, 'VALUES', values), patch.object(prepare, 'TEST', test):
                prepare.apply(plan)
            self.assertEqual(values.read_text(), original.replace('v0.0.1', 'v0.0.2').replace('v0.2.1', 'v0.2.2'))
            self.assertEqual(test.read_text(), 'value: quay.io/kubescape/operator:v0.2.2\n')

    def test_invalid_transition_rejected(self):
        plan = {'compatibility': 'unverified', 'updates': [{'key': 'storage', 'repository': 'storage', 'old': 'v0.0.1', 'new': 'v0.1.0'}]}
        with self.assertRaises(ValueError):
            prepare.apply(plan)


class PublicationTests(unittest.TestCase):
    def test_human_review_freezes(self):
        body = 'text'
        import hashlib
        head = 'a' * 40
        marker = f'\n<!-- component-updates:v1 head={head} body={hashlib.sha256(body.encode()).hexdigest()} -->'
        pr = {'user': {'login': publish.BOT}, 'draft': True, 'base': {'ref': 'main', 'repo': {'full_name': publish.REPO}}, 'head': {'sha': head}, 'body': body + marker, 'number': 1}
        with patch.object(publish, 'pages', return_value=[{'user': {'login': 'human', 'type': 'User'}}]):
            with self.assertRaisesRegex(ValueError, 'human review'):
                publish.ensure_unadopted(pr, head)

    def test_human_commit_and_readiness_freeze(self):
        import hashlib
        head = 'a' * 40
        body = 'original'
        pr = {'user': {'login': publish.BOT}, 'draft': True, 'base': {'ref': 'main', 'repo': {'full_name': publish.REPO}}, 'head': {'sha': head},
              'body': body + f"\n<!-- component-updates:v1 head={head} body={hashlib.sha256(body.encode()).hexdigest()} -->", 'number': 4}
        with patch.object(publish, 'pages', side_effect=[[], [], [{'author': {'login': 'alice'}}]]):
            with self.assertRaisesRegex(ValueError, 'human or unknown commit'):
                publish.ensure_unadopted(pr, head)
        with patch.object(publish, 'pages', side_effect=[[], [], [], [{'event': 'ready_for_review', 'actor': {'login': 'alice', 'type': 'User'}}]]):
            with self.assertRaisesRegex(ValueError, 'readiness'):
                publish.ensure_unadopted(pr, head)
        with patch.object(publish, 'pages', return_value=[]):
            publish.ensure_unadopted(pr, head)

    def test_no_updates_do_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.json'
            path.write_text(json.dumps({'updates': []}))
            with patch.dict('os.environ', {'GITHUB_REPOSITORY': publish.REPO, 'GITHUB_REF': 'refs/heads/main'}), patch.object(publish, 'api') as api:
                publish.publish(str(path), 'abc')
                api.assert_not_called()

    def test_changed_base_prevents_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.json'
            path.write_text(json.dumps({'updates': [{'key': 'storage'}]}))
            with patch.dict('os.environ', {'GITHUB_REPOSITORY': publish.REPO, 'GITHUB_REF': 'refs/heads/main'}), patch.object(publish, 'api', return_value={'object': {'sha': 'different'}}):
                with self.assertRaisesRegex(ValueError, 'main changed'):
                    publish.publish(str(path), 'expected')

    def test_retargeted_draft_is_rejected_before_activity_queries(self):
        head = 'a' * 40
        for base in ({'ref': 'release', 'repo': {'full_name': publish.REPO}},
                     {'ref': 'main', 'repo': {'full_name': 'other/repo'}}, None):
            with self.subTest(base=base), patch.object(publish, 'pages', return_value=[]) as pages:
                pr = {'user': {'login': publish.BOT}, 'draft': True,
                      'head': {'sha': head}, 'base': base, 'number': 1,
                      'body': '\n<!-- component-updates:v1 head=' + head + ' body=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 -->'}
                with self.assertRaisesRegex(ValueError, 'base'):
                    publish.ensure_unadopted(pr, head)
                pages.assert_not_called()

    def test_wrong_repository_cannot_publish(self):
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'other/repo', 'GITHUB_REF': 'refs/heads/main'}):
            with self.assertRaisesRegex(ValueError, 'restricted'):
                publish.publish('unused', 'unused')

    def test_description_edits_freeze(self):
        head = 'a' * 40
        pr = {'user': {'login': publish.BOT}, 'draft': True, 'base': {'ref': 'main', 'repo': {'full_name': publish.REPO}}, 'head': {'sha': head}, 'body': 'edited\n<!-- component-updates:v1 head=' + head + ' body=' + '0' * 64 + ' -->'}
        with self.assertRaisesRegex(ValueError, 'edited'):
            publish.ensure_unadopted(pr, head)


if __name__ == '__main__':
    unittest.main()
