import unittest
from unittest.mock import patch

from agents_schema import dbt, lookml, omni, osi, skills, snowflake_semantic
from agents_schema.skills import SkillFile


class FakeDestination:
    def __init__(self):
        self.calls = []

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))

    def delete_rows(self, table, key_columns, rows):
        self.calls.append(("delete", table.name, key_columns, list(rows)))


class DestinationContext:
    def __init__(self, dest):
        self.dest = dest

    def __enter__(self):
        return self.dest

    def __exit__(self, exc_type, exc, tb):
        return None


class ConnectorRootTests(unittest.TestCase):
    def test_dbt_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"warehouse": {"type": "snowflake"}, "metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.dbt.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.dbt._load_manifest", return_value={"nodes": {}}),
            patch("builtins.print"),
            patch("agents_schema.dbt.publish_builtin_skill"),
        ):
            dbt.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"dbt"})
        self.assertEqual([call[0] for call in dest.calls[1:4]], ["replace", "replace", "replace"])

    def test_lookml_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"warehouse": {"type": "snowflake"}, "metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.lookml.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.lookml._load_lookml_files", return_value=[]),
            patch("builtins.print"),
            patch("agents_schema.lookml.publish_builtin_skill"),
        ):
            lookml.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"lookml"})
        self.assertEqual([call[0] for call in dest.calls[1:5]], ["replace", "replace", "replace", "replace"])

    def test_omni_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.omni.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.omni._ingest"),
            patch("builtins.print"),
        ):
            omni.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"omni"})
        self.assertEqual([call[0] for call in dest.calls[1:6]], ["replace", "replace", "replace", "replace", "replace"])

    def test_osi_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"warehouse": {"type": "snowflake"}, "metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.osi.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.osi._load_osi_files", return_value=[]),
            patch("builtins.print"),
            patch("agents_schema.osi.publish_builtin_skill"),
        ):
            osi.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"osi"})
        self.assertEqual([call[0] for call in dest.calls[1:6]], ["replace"] * 5)

    def test_skills_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {
            "warehouse": {"type": "snowflake"},
            "metadata_connection": {"path": ".", "provider": "fivetran"},
        }
        skill = SkillFile(
            key="skill/revenue",
            content="# Revenue\n",
            uses=(("schema", "QUICKSTART_FINANCE"), ("table", "QUICKSTART_FINANCE.ARR_SNAPSHOT")),
        )

        with (
            patch("agents_schema.skills.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.skills._load_skill_files", return_value=[skill]),
            patch("builtins.print"),
            patch("agents_schema.skills.publish_builtin_skill"),
        ):
            skills.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"skills"})
        self.assertEqual(dest.calls[1][0], "upsert")
        self.assertEqual(dest.calls[1][1], "agents.root")
        self.assertEqual(dest.calls[1][2], [("fivetran", "skill/revenue", "# Revenue\n")])
        self.assertEqual(dest.calls[2], ("replace", "agents.skill_use"))
        self.assertEqual(dest.calls[3][0], "insert")
        self.assertEqual(dest.calls[3][1], "agents.skill_use")

    def test_snowflake_semantic_run_upserts_root_overview_then_pointer_rows(self):
        dest = FakeDestination()
        cfg = {
            "warehouse": {"type": "snowflake"},
            "metadata_connection": {"semantic_views": ["ANALYTICS.FINANCE.REVENUE"]},
        }

        with (
            patch(
                "agents_schema.snowflake_semantic.open_destination",
                return_value=DestinationContext(dest),
            ),
            patch("builtins.print"),
            patch("agents_schema.snowflake_semantic.publish_builtin_skill"),
        ):
            snowflake_semantic.run(cfg)

        self.assertEqual(len(dest.calls), 2)
        # first call: overview row
        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual(dest.calls[0][1], "agents.root")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"snowflake_semantic"})
        self.assertEqual({row[1] for row in dest.calls[0][2]}, {"overview"})
        # second call: per-view pointer row
        self.assertEqual(dest.calls[1][0], "upsert")
        self.assertEqual(dest.calls[1][1], "agents.root")
        self.assertEqual(dest.calls[1][2][0][0], "snowflake_semantic")
        self.assertEqual(dest.calls[1][2][0][1], "semantic_view/ANALYTICS.FINANCE.REVENUE")
        self.assertIn("Snowflake object: `ANALYTICS.FINANCE.REVENUE`", dest.calls[1][2][0][2])

    def test_publish_skill_upserts_one_root_row_and_refreshes_its_uses(self):
        dest = FakeDestination()
        content = (
            "---\n"
            "uses:\n"
            "  schemas:\n"
            "    - ZENDESK\n"
            "  tables:\n"
            "    - ZENDESK.TICKET\n"
            "---\n"
            "# Zendesk\n"
        )

        skill = skills.publish_skill(dest, "fivetran", "skill/zendesk", content)

        self.assertEqual(skill.uses, (("schema", "ZENDESK"), ("table", "ZENDESK.TICKET")))
        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"skills"})
        self.assertEqual(dest.calls[1], ("upsert", "agents.root", [("fivetran", "skill/zendesk", content)]))
        self.assertEqual(dest.calls[2], ("delete", "agents.skill_use", ("provider", "skill_key"), [("fivetran", "skill/zendesk")]))
        self.assertEqual(
            dest.calls[3],
            (
                "upsert",
                "agents.skill_use",
                [
                    ("fivetran", "skill/zendesk", "schema", "ZENDESK"),
                    ("fivetran", "skill/zendesk", "table", "ZENDESK.TICKET"),
                ],
            ),
        )

    def test_publish_skill_without_uses_only_deletes_stale_use_rows(self):
        dest = FakeDestination()

        skill = skills.publish_skill(dest, "fivetran", "skill/zendesk", "# Zendesk\n")

        self.assertEqual(skill.uses, ())
        self.assertEqual(dest.calls[-1], ("delete", "agents.skill_use", ("provider", "skill_key"), [("fivetran", "skill/zendesk")]))


if __name__ == "__main__":
    unittest.main()
