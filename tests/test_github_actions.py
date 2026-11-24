import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_ROOT = REPO_ROOT / ".github" / "actions"
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
RUNTIME_ACTION = ACTION_ROOT / "agents-schema-runtime" / "action.yml"
WORKFLOW_REFERENCE = re.compile(
    r"uses:\s+dbt-labs/agents_schema/\.github/workflows/\S+@([^\s]+)"
)


class GitHubActionsTests(unittest.TestCase):
    def test_reusable_workflows_declare_least_privilege_permissions(self):
        # Every reusable workflow must state its permissions explicitly: read-only
        # contents, plus `id-token: write` only where it is requested for keyless auth.
        workflows = sorted(WORKFLOW_ROOT.glob("agents-schema-*.yml"))

        self.assertTrue(workflows)
        for workflow in workflows:
            permissions = yaml.safe_load(workflow.read_text()).get("permissions")
            with self.subTest(workflow=workflow.name):
                self.assertIsInstance(permissions, dict)
                self.assertEqual(permissions.get("contents"), "read")
                self.assertLessEqual(set(permissions) - {"contents", "id-token"}, set())

    def test_documented_callers_grant_the_permissions_the_called_workflows_request(self):
        # A called workflow cannot be granted more than its caller, so a caller that omits
        # a permission the reusable workflow requests fails at startup. Check every caller
        # shown in the setup guides and examples against the workflow it calls.
        levels = {"none": 0, "read": 1, "write": 2}
        called = re.compile(r"workflows/(agents-schema-[\w-]+)\.yml@")
        sources = [(p, p.read_text()) for p in sorted((REPO_ROOT / "examples" / "workflows").glob("*.yml"))]
        for guide in sorted(REPO_ROOT.glob("*-setup.md")):
            blocks = re.findall(r"```yaml\n(.*?)```", guide.read_text(), re.S)
            sources += [(guide, b) for b in blocks if "uses: dbt-labs/agents_schema" in b]

        checked = 0
        for path, text in sources:
            doc = yaml.safe_load(text)
            for job_name, job in doc["jobs"].items():
                match = called.search(job["uses"])
                requested = yaml.safe_load((WORKFLOW_ROOT / f"{match.group(1)}.yml").read_text())["permissions"]
                granted = job.get("permissions", doc.get("permissions")) or {}
                for scope, level in requested.items():
                    checked += 1
                    with self.subTest(source=path.name, job=job_name, scope=scope):
                        self.assertGreaterEqual(
                            levels[granted.get(scope, "none")], levels[level],
                            f"{path.name}: {job_name} must grant {scope}: {level}",
                        )
        self.assertGreater(checked, 20)

    def test_reusable_workflows_use_colocated_composite_actions(self):
        workflows = sorted(WORKFLOW_ROOT.glob("agents-schema-*.yml"))

        self.assertTrue(workflows)
        for workflow in workflows:
            contents = workflow.read_text()
            with self.subTest(workflow=workflow.name):
                self.assertIn("uses: $/.github/actions/", contents)
                self.assertNotIn(
                    "uses: dbt-labs/agents_schema/.github/actions/", contents
                )

    def test_composite_actions_run_the_bundled_cli(self):
        actions = sorted(ACTION_ROOT.glob("*/action.yml"))

        self.assertTrue(actions)
        for action in actions:
            contents = action.read_text()
            with self.subTest(action=action.parent.name):
                self.assertIn(
                    'uvx --from "$GITHUB_ACTION_PATH/../../.."', contents
                )
                self.assertNotIn('uvx --from "agents-schema==', contents)

    def test_reusable_workflows_report_runtime_before_ingestion(self):
        workflows = sorted(WORKFLOW_ROOT.glob("agents-schema-*.yml"))
        runtime_reference = "uses: $/.github/actions/agents-schema-runtime"

        self.assertTrue(workflows)
        for workflow in workflows:
            contents = workflow.read_text()
            with self.subTest(workflow=workflow.name):
                self.assertEqual(contents.count(runtime_reference), 1)
                self.assertIn("workflow-ref: ${{ job.workflow_ref }}", contents)
                self.assertIn("workflow-sha: ${{ job.workflow_sha }}", contents)
                self.assertLess(
                    contents.index(runtime_reference),
                    contents.rindex("uses: $/.github/actions/"),
                )

    def test_runtime_action_reports_ref_commit_and_cli_version(self):
        contents = RUNTIME_ACTION.read_text()

        self.assertIn("Agents Schema workflow ref:", contents)
        self.assertIn("Agents Schema workflow commit:", contents)
        self.assertIn("Agents Schema CLI version:", contents)
        self.assertIn("::notice title=Agents Schema runtime::", contents)
        self.assertIn("escape_workflow_command", contents)
        self.assertIn('} >> "$GITHUB_STEP_SUMMARY"', contents)
        self.assertNotIn("$GITHUB_OUTPUT", contents)

    def test_customer_workflow_references_use_v0(self):
        reference_files = [
            REPO_ROOT / "README.md",
            *sorted(REPO_ROOT.glob("*-setup.md")),
            *sorted((REPO_ROOT / "examples" / "workflows").glob("*.yml")),
        ]
        references = []

        for path in reference_files:
            for version in WORKFLOW_REFERENCE.findall(path.read_text()):
                references.append((path, version))

        self.assertTrue(references)
        for path, version in references:
            with self.subTest(path=path.relative_to(REPO_ROOT), version=version):
                self.assertEqual(version, "v0")


if __name__ == "__main__":
    unittest.main()
