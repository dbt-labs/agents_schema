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

    def test_composite_actions_do_not_expand_expressions_inside_shell_scripts(self):
        # `${{ inputs.x }}` inside a `run:` block is pasted into the script before the shell parses it,
        # so a value containing quotes or `$(...)` would run as code. Pass inputs through `env:` instead.
        actions = sorted(ACTION_ROOT.glob("*/action.yml"))

        self.assertTrue(actions)
        for action in actions:
            steps = yaml.safe_load(action.read_text())["runs"]["steps"]
            for step in steps:
                with self.subTest(action=action.parent.name, step=step.get("name")):
                    self.assertNotIn("${{", step.get("run", ""))

    def test_workflows_do_not_expand_expressions_inside_shell_scripts_either(self):
        for workflow in sorted(WORKFLOW_ROOT.glob("*.yml")):
            jobs = yaml.safe_load(workflow.read_text()).get("jobs", {})
            for job_name, job in jobs.items():
                for step in job.get("steps", []):
                    with self.subTest(workflow=workflow.name, job=job_name, step=step.get("name")):
                        self.assertNotIn("${{", step.get("run", ""))

    def test_skills_action_hands_its_inputs_to_the_script_through_env(self):
        steps = yaml.safe_load((ACTION_ROOT / "agents-schema-skills" / "action.yml").read_text())["runs"]["steps"]
        step = next(s for s in steps if "agents-schema skills" in s.get("run", ""))

        self.assertEqual(step["env"]["AGENTS_SCHEMA_SKILLS_DIR"], "${{ inputs.skills-dir }}")
        self.assertEqual(step["env"]["AGENTS_SCHEMA_SKILLS_PROVIDER"], "${{ inputs.provider }}")
        self.assertIn('"$AGENTS_SCHEMA_SKILLS_DIR"', step["run"])
        self.assertIn('"$AGENTS_SCHEMA_SKILLS_PROVIDER"', step["run"])

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
