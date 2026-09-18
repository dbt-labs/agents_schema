import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_ROOT = REPO_ROOT / ".github" / "actions"
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
WORKFLOW_REFERENCE = re.compile(
    r"uses:\s+dbt-labs/agents_schema/\.github/workflows/\S+@([^\s]+)"
)


class GitHubActionsTests(unittest.TestCase):
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
