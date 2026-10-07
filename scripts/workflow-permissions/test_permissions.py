"""Validate local reusable-workflow token contracts.

Run: python3 -B -m unittest discover -s scripts/workflow-permissions -v
Requires PyYAML (also used by the existing allowlist tooling).
Scope reference: https://github.com/actions/languageservices/blob/4043eda158e16579cc5fb1b0b07a4bce2a76f0b5/workflow-parser/src/workflow-v1.0.json
"""

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

# read-all includes every readable scope, but does not grant OIDC/Copilot writes.
READ_SCOPES = (
    "actions", "artifact-metadata", "attestations", "checks", "code-quality",
    "contents", "deployments", "discussions", "drives", "issues", "models",
    "packages", "pages", "pull-requests", "repository-projects",
    "security-events", "statuses", "vulnerability-alerts",
)
WRITE_ONLY_SCOPES = ("id-token", "copilot-requests")
LEVELS = {"none": 0, "read": 1, "write": 2}
ROOT = Path(__file__).resolve().parents[2]


def expand(permissions):
    """Explicit maps deny omitted scopes; shorthand grants all applicable scopes."""
    result = dict.fromkeys((*READ_SCOPES, *WRITE_ONLY_SCOPES), 0)
    if permissions == "read-all":
        result.update(dict.fromkeys(READ_SCOPES, 1))
    elif permissions == "write-all":
        result.update(dict.fromkeys(result, 2))
        result.update({"models": 1, "vulnerability-alerts": 1})
    else:
        for scope, level in permissions.items():
            if scope not in result:
                raise ValueError(f"Unknown permission scope: {scope}")
            result[scope] = LEVELS[level]
    return result


def violations(workflows):
    """Check callee defaults and every nested job against each caller ceiling."""
    errors = []

    def require(requested, ceiling, location):
        denied = [scope for scope, level in requested.items() if level > ceiling[scope]]
        if denied:
            errors.append(f"{location}: insufficient permissions: {', '.join(denied)}")

    def visit(path, ceiling, chain):
        workflow = workflows[path]
        defaults = expand(workflow["permissions"])
        if ceiling is not None:
            require(defaults, ceiling, f"{' -> '.join(chain)} workflow defaults")
        for name, job in workflow["jobs"].items():
            permissions = expand(job.get("permissions", workflow["permissions"]))
            location = f"{' -> '.join(chain)} / {name}"
            if ceiling is not None:
                require(permissions, ceiling, location)
            target = job.get("uses", "")
            if target.startswith("./.github/workflows/"):
                target = target[2:]
                if target in chain:
                    raise ValueError(f"Recursive workflow call: {location}")
                effective = permissions if ceiling is None else {
                    scope: min(level, ceiling[scope]) for scope, level in permissions.items()
                }
                visit(target, effective, [*chain, target])

    for path in workflows:
        visit(path, None, [path])
    return errors


class PermissionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            str(path.relative_to(ROOT)): yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for path in (ROOT / ".github/workflows").iterdir()
            if path.suffix in (".yaml", ".yml")
        }

    def test_workflow_defaults_are_read_only(self):
        for path, workflow in self.workflows.items():
            with self.subTest(workflow=path):
                self.assertEqual(workflow["permissions"], "read-all")

    def test_all_local_calls_and_nested_jobs_are_compatible(self):
        self.assertEqual(violations(self.workflows), [])

    def test_caller_write_grants_remain_minimal(self):
        expected = {
            ("00-cicd.yaml", "helm-chart-update"): {"contents"},
            ("00-cicd.yaml", "helm-release"): {"contents", "attestations", "id-token"},
            ("inspektor-trigger-e2e-tests.yaml", "call-e2e-tests"): {"checks"},
        }
        for (path, job), writes in expected.items():
            with self.subTest(workflow=path, job=job):
                permissions = self.workflows[f".github/workflows/{path}"]["jobs"][job]["permissions"]
                self.assertEqual({scope for scope, level in permissions.items() if level == "write"}, writes)

    def test_omitted_scopes_are_denied(self):
        permissions = expand({"contents": "write"})
        self.assertEqual(permissions["contents"], 2)
        self.assertEqual(permissions["actions"], 0)
        self.assertEqual(permissions["id-token"], 0)

    def test_read_all_does_not_grant_write_only_scopes(self):
        permissions = expand("read-all")
        self.assertTrue(all(permissions[scope] == 1 for scope in READ_SCOPES))
        self.assertTrue(all(permissions[scope] == 0 for scope in WRITE_ONLY_SCOPES))

    def test_original_three_callers_fail_default_compatibility(self):
        workflows = deepcopy(self.workflows)
        workflows[".github/workflows/00-cicd.yaml"]["jobs"]["helm-chart-update"]["permissions"] = {"contents": "write"}
        workflows[".github/workflows/00-cicd.yaml"]["jobs"]["helm-release"]["permissions"] = {
            "contents": "write", "id-token": "write", "attestations": "write",
        }
        workflows[".github/workflows/inspektor-trigger-e2e-tests.yaml"]["jobs"]["call-e2e-tests"]["permissions"] = {
            "contents": "read", "checks": "write",
        }
        defaults = [error for error in violations(workflows) if "workflow defaults" in error]
        # The release caller also fails at the nested 03 -> 02 boundary.
        self.assertEqual(len(defaults), 4)
        for callee in ("01-update_tag.yaml", "03-helm-release.yaml", "relevancy-e2e-test.yaml", "02-e2e-test.yaml"):
            self.assertTrue(any(callee in error for error in defaults), callee)

    def test_nested_call_cannot_restore_denied_permissions(self):
        workflows = deepcopy(self.workflows)
        workflows[".github/workflows/03-helm-release.yaml"]["jobs"]["e2e-test"]["permissions"] = {"contents": "read"}
        errors = violations(workflows)
        self.assertTrue(any("02-e2e-test.yaml workflow defaults" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
