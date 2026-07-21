import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agents-schema"


class PluginMarketplaceTests(unittest.TestCase):
    def test_marketplace_installs_agents_schema_plugin(self):
        marketplace = json.loads(MARKETPLACE_PATH.read_text())

        self.assertEqual(marketplace["name"], "agents-schema")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "agents-schema")
        self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/agents-schema"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )

    def test_plugin_contains_schema_search_and_connection_skills(self):
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
        skill_root = PLUGIN_ROOT / manifest["skills"]
        skill_names = {path.parent.name for path in skill_root.glob("*/SKILL.md")}

        self.assertEqual(skill_names, {"agents-schema-search", "connect-warehouse"})
        schema_skill = (skill_root / "agents-schema-search" / "SKILL.md").read_text()
        self.assertIn("SELECT * FROM AGENTS.ROOT ORDER BY provider, key;", schema_skill)
        connection_references = {
            path.stem for path in (skill_root / "connect-warehouse" / "references").glob("*.md")
        }
        self.assertEqual(connection_references, {"snowflake", "bigquery", "databricks"})


if __name__ == "__main__":
    unittest.main()
