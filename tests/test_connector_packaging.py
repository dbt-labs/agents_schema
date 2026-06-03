import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

POWERBI_PACKAGING = {
    "slug": "powerbi",
    "setup": "powerbi-setup.md",
    "command": "powerbi",
    "input": "metadata-path",
}


class ConnectorPackagingTests(unittest.TestCase):
    def test_powerbi_has_first_class_packaging(self):
        slug = POWERBI_PACKAGING["slug"]
        action = REPO_ROOT / ".github" / "actions" / f"agents-schema-{slug}" / "action.yml"
        workflow = REPO_ROOT / ".github" / "workflows" / f"agents-schema-{slug}.yml"
        setup = REPO_ROOT / POWERBI_PACKAGING["setup"]
        example = REPO_ROOT / "examples" / "workflows" / f"{slug}.yml"

        self.assertTrue(action.exists(), action)
        self.assertTrue(workflow.exists(), workflow)
        self.assertTrue(setup.exists(), setup)
        self.assertTrue(example.exists(), example)

        action_text = action.read_text()
        self.assertIn(f"agents-schema {POWERBI_PACKAGING['command']}", action_text)
        self.assertIn(f"--{POWERBI_PACKAGING['input']}", action_text)

        workflow_data = yaml.safe_load(workflow.read_text())
        self.assertEqual(workflow_data["jobs"]["ingest"]["steps"][0]["uses"], "actions/checkout@v4")
        run_step = workflow_data["jobs"]["ingest"]["steps"][1]
        self.assertEqual(
            run_step["uses"],
            f"fivetran/agents_schema/.github/actions/agents-schema-{slug}@v0.0.6",
        )
        self.assertIn(POWERBI_PACKAGING["input"], run_step["with"])

        setup_text = setup.read_text()
        self.assertIn("WAREHOUSE_CREDENTIALS", setup_text)
        self.assertIn(f"agents-schema-{slug}.yml@v0.0.6", setup_text)


if __name__ == "__main__":
    unittest.main()
