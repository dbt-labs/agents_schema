import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

SUPPORTED_SOURCE_PACKAGING = {
    "dbt": {
        "slug": "dbt",
        "setup": "dbt-setup.md",
        "command": "dbt",
        "input": "dbt-project-dir",
        "cli_input": "project-dir",
    },
    "lookml": {
        "slug": "looker",
        "setup": "looker-setup.md",
        "command": "looker",
        "input": "lookml-dir",
    },
    "osi": {
        "slug": "osi",
        "setup": "osi-setup.md",
        "command": "osi",
        "input": "osi-dir",
    },
    "powerbi": {
        "slug": "powerbi",
        "setup": "powerbi-setup.md",
        "command": "powerbi",
        "input": "metadata-path",
    },
    "tableau": {
        "slug": "tableau",
        "setup": "tableau-setup.md",
        "command": "tableau",
        "input": "metadata-path",
    },
    "dbt_semantic": {
        "slug": "dbt-semantic",
        "setup": "dbt-semantic-setup.md",
        "command": "dbt-semantic",
        "input": "semantic-manifest",
    },
    "datahub": {
        "slug": "datahub",
        "setup": "datahub-setup.md",
        "command": "datahub",
        "input": "metadata-path",
    },
    "openmetadata": {
        "slug": "openmetadata",
        "setup": "openmetadata-setup.md",
        "command": "openmetadata",
        "input": "metadata-path",
    },
    "atlan": {
        "slug": "atlan",
        "setup": "atlan-setup.md",
        "command": "atlan",
        "input": "metadata-path",
    },
    "alation": {
        "slug": "alation",
        "setup": "alation-setup.md",
        "command": "alation",
        "input": "metadata-path",
    },
    "collibra": {
        "slug": "collibra",
        "setup": "collibra-setup.md",
        "command": "collibra",
        "input": "metadata-path",
    },
    "metabase": {
        "slug": "metabase",
        "setup": "metabase-setup.md",
        "command": "metabase",
        "input": "metadata-path",
    },
    "cube": {
        "slug": "cube",
        "setup": "cube-setup.md",
        "command": "cube",
        "input": "metadata-path",
    },
}


class ConnectorPackagingTests(unittest.TestCase):
    def test_supported_sources_have_first_class_packaging(self):
        for provider, packaging in SUPPORTED_SOURCE_PACKAGING.items():
            with self.subTest(provider=provider):
                slug = packaging["slug"]
                action = REPO_ROOT / ".github" / "actions" / f"agents-schema-{slug}" / "action.yml"
                workflow = REPO_ROOT / ".github" / "workflows" / f"agents-schema-{slug}.yml"
                setup = REPO_ROOT / packaging["setup"]
                example = REPO_ROOT / "examples" / "workflows" / f"{slug}.yml"

                self.assertTrue(action.exists(), action)
                self.assertTrue(workflow.exists(), workflow)
                self.assertTrue(setup.exists(), setup)
                self.assertTrue(example.exists(), example)

                action_text = action.read_text()
                self.assertIn(f"agents-schema {packaging['command']}", action_text)
                self.assertIn(f"--{packaging.get('cli_input', packaging['input'])}", action_text)

                workflow_data = yaml.safe_load(workflow.read_text())
                self.assertEqual(workflow_data["jobs"]["ingest"]["steps"][0]["uses"], "actions/checkout@v4")
                run_step = workflow_data["jobs"]["ingest"]["steps"][1]
                self.assertEqual(
                    run_step["uses"],
                    f"fivetran/agents_schema/.github/actions/agents-schema-{slug}@v0.0.6",
                )
                self.assertIn(packaging["input"], run_step["with"])

                setup_text = setup.read_text()
                self.assertIn("WAREHOUSE_CREDENTIALS", setup_text)
                self.assertIn(f"agents-schema-{slug}.yml@v0.0.6", setup_text)


if __name__ == "__main__":
    unittest.main()
