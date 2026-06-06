import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import cli
from agents_schema.skills import _load_skill_files, _parse_uses_frontmatter


class SkillsTests(unittest.TestCase):
    def test_load_skill_files_discovers_markdown_recursively_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_path = root / "revenue" / "arr.md"
            skill_path.parent.mkdir()
            content = (
                "---\n"
                "uses:\n"
                "  schemas:\n"
                "    - QUICKSTART_FINANCE\n"
                "  tables:\n"
                "    - QUICKSTART_FINANCE.ARR_SNAPSHOT\n"
                "---\n"
                "# ARR\n"
            )
            skill_path.write_text(content)

            skills = _load_skill_files(root)

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].key, "skill/revenue/arr")
        self.assertEqual(skills[0].content, content)
        self.assertEqual(
            skills[0].uses,
            (("schema", "QUICKSTART_FINANCE"), ("table", "QUICKSTART_FINANCE.ARR_SNAPSHOT")),
        )
        self.assertEqual(skills[0].warnings, ())

    def test_load_skill_files_rejects_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "no \\*.md skill files"):
                _load_skill_files(Path(tmp))

    def test_parse_uses_frontmatter_accepts_missing_frontmatter(self):
        uses, warnings = _parse_uses_frontmatter("# Revenue\n")

        self.assertEqual(uses, ())
        self.assertEqual(warnings, ())

    def test_parse_uses_frontmatter_warns_for_malformed_uses(self):
        content = "---\nuses:\n  tables: FINANCE.ARR_SNAPSHOT\n---\n# Revenue\n"

        uses, warnings = _parse_uses_frontmatter(content)

        self.assertEqual(uses, ())
        self.assertEqual(warnings, ("uses.tables must be a list of strings",))

    def test_parse_uses_frontmatter_warns_for_unqualified_tables(self):
        content = "---\nuses:\n  tables:\n    - ARR_SNAPSHOT\n---\n# Revenue\n"

        uses, warnings = _parse_uses_frontmatter(content)

        self.assertEqual(uses, ())
        self.assertEqual(warnings, ("uses.tables entries must be schema-qualified",))

    def test_cli_dispatches_skills_with_provider(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.skills.run") as run,
        ):
            result = cli.main(["skills", "--skills-dir", "skills", "--provider", "fivetran"])

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            {
                "warehouse": {"type": "snowflake"},
                "metadata_connection": {
                    "type": "skills",
                    "path": "skills",
                    "provider": "fivetran",
                },
            }
        )

    def test_cli_defaults_skills_provider_to_user(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.skills.run") as run,
        ):
            result = cli.main(["skills", "--skills-dir", "skills"])

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            {
                "warehouse": {"type": "snowflake"},
                "metadata_connection": {
                    "type": "skills",
                    "path": "skills",
                    "provider": "user",
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
