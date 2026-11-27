import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import cli, skills
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

    def test_parse_uses_frontmatter_stores_a_repeated_entry_once_and_warns(self):
        content = (
            "---\nuses:\n  schemas: [sales, sales, finance]\n  tables: [A.B, A.B]\n---\n# Revenue\n"
        )

        uses, warnings = _parse_uses_frontmatter(content)

        self.assertEqual(uses, (("schema", "sales"), ("schema", "finance"), ("table", "A.B")))
        self.assertEqual(len(warnings), 1)
        self.assertIn("schema sales", warnings[0])
        self.assertIn("table A.B", warnings[0])
        self.assertIn("stored once", warnings[0])

    def test_distinct_entries_produce_no_warning(self):
        uses, warnings = _parse_uses_frontmatter("---\nuses:\n  schemas: [sales, Sales]\n---\n# Revenue\n")

        self.assertEqual(uses, (("schema", "sales"), ("schema", "Sales")))
        self.assertEqual(warnings, ())

    def test_run_writes_a_repeated_schema_as_one_skill_use_row(self):
        # BigQuery has no unique constraint: two identical rows would be stored, and fixing the file later would
        # keep both because each still matches the one remaining entry.
        class Destination:
            def __init__(self):
                self.reconciled = {}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def upsert_rows(self, table, rows):
                pass

            def reconcile_rows(self, table, rows, scope=None):
                self.reconciled[table.name] = list(rows)

        dest = Destination()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "revenue.md").write_text("---\nuses:\n  schemas: [sales, sales]\n---\n# Revenue\n")
            cfg = {
                "warehouse": {"type": "bigquery"},
                "metadata_connection": {"path": tmp, "provider": "fivetran"},
            }
            stderr = io.StringIO()
            with (
                patch("agents_schema.skills.open_destination", return_value=dest),
                patch("agents_schema.skills.publish_builtin_skill"),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(stderr),
            ):
                skills.run(cfg)

        self.assertEqual(dest.reconciled["AGENTS.SKILL_USE"], [("fivetran", "skill/revenue", "schema", "sales")])
        self.assertIn("stored once", stderr.getvalue())

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

    def test_cli_dispatches_snowflake_semantic_views(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.snowflake_semantic.run") as run,
        ):
            result = cli.main(
                [
                    "snowflake-semantic",
                    "--semantic-view",
                    "ANALYTICS.FINANCE.REVENUE",
                    "--semantic-view",
                    "ANALYTICS.SALES.PIPELINE",
                ]
            )

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            {
                "warehouse": {"type": "snowflake"},
                "metadata_connection": {
                    "type": "snowflake-semantic",
                    "semantic_views": ["ANALYTICS.FINANCE.REVENUE", "ANALYTICS.SALES.PIPELINE"],
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
