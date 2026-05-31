import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import memory
from agents_schema.config import ConfigError


class FakeDestination:
    def __init__(self):
        self.calls = []

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))


class DestinationContext:
    def __init__(self, dest):
        self.dest = dest

    def __enter__(self):
        return self.dest

    def __exit__(self, exc_type, exc, tb):
        return None


class MemoryTests(unittest.TestCase):
    def test_load_memory_file_requires_memories_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text("memories: {}\n")

            with self.assertRaisesRegex(ConfigError, "memories must be a list"):
                memory.load_memory_file(path)

    def test_load_memory_file_rejects_unknown_memory_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: typo
                        memory_kind: unit_rule
                        content: typo should fail
                        summmary: typo should fail
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "unknown field"):
                memory.load_memory_file(path)

    def test_load_memory_file_rejects_duplicate_memory_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: duplicate
                        memory_kind: unit_rule
                        content: duplicate
                      - memory_id: duplicate
                        memory_kind: unit_rule
                        content: duplicate
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "duplicate memory"):
                memory.load_memory_file(path)

    def test_load_memory_file_rejects_column_anchor_without_locator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: missing_locator
                        memory_kind: unit_rule
                        content: Missing locator.
                        anchors:
                          - anchor_id: amount_due
                            anchor_type: column
                            table_name: invoice
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "column anchors require table_name and column_name"):
                memory.load_memory_file(path)

    def test_load_memory_file_rejects_locator_not_allowed_for_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: cross_wired
                        memory_kind: metric_rule
                        content: A metric anchor should not carry a table_name.
                        anchors:
                          - anchor_id: revenue
                            anchor_type: metric
                            metric_id: revenue
                            table_name: invoice
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "metric anchors do not use table_name"):
                memory.load_memory_file(path)

    def test_load_memory_file_rejects_confidence_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: too_confident
                        memory_kind: unit_rule
                        content: Confidence must be 0..1.
                        confidence: 2
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "confidence must be between 0 and 1"):
                memory.load_memory_file(path)

    def test_load_memory_file_builds_relationship_anchor_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: ticket_assignee_join
                        memory_kind: join_rule
                        content: Join ticket.assignee_id to user.id.
                        anchors:
                          - anchor_id: ticket_to_user
                            anchor_type: relationship
                            relationship_name: ticket_to_user
                            from_schema: zendesk
                            from_table: ticket
                            from_columns: [assignee_id]
                            to_schema: zendesk
                            to_table: user
                            to_columns: [id]
                    """
                )
            )

            _, anchors = memory.load_memory_file(path)

        self.assertEqual(
            anchors,
            [
                (
                    "ticket_assignee_join",
                    "ticket_to_user",
                    "relationship",
                    None,  # schema_name
                    None,  # table_name
                    None,  # column_name
                    None,  # metric_id
                    "ticket_to_user",
                    "zendesk",
                    "ticket",
                    ["assignee_id"],
                    "zendesk",
                    "user",
                    ["id"],
                )
            ],
        )

    def test_load_memory_file_rejects_wrong_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: bad_content
                        memory_kind: unit_rule
                        content: [not, scalar]
                    """
                )
            )

            with self.assertRaisesRegex(ConfigError, "content must be a string"):
                memory.load_memory_file(path)

    def test_load_memory_file_builds_memory_and_anchor_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: stripe_amounts_are_cents
                        memory_kind: unit_rule
                        title: Stripe amounts
                        content: Divide Stripe amount columns by 100 for dollars.
                        source: memories.yaml
                        confidence: 0.9
                        anchors:
                          - anchor_id: invoice_amount_due
                            anchor_type: column
                            schema_name: stripe
                            table_name: invoice
                            column_name: amount_due
                    """
                )
            )

            memories, anchors = memory.load_memory_file(path)

        self.assertEqual(
            memories,
            [
                (
                    "stripe_amounts_are_cents",
                    "unit_rule",
                    "Stripe amounts",
                    "Divide Stripe amount columns by 100 for dollars.",
                    "memories.yaml",
                    0.9,
                )
            ],
        )
        self.assertEqual(
            anchors,
            [
                (
                    "stripe_amounts_are_cents",
                    "invoice_amount_due",
                    "column",
                    "stripe",  # schema_name
                    "invoice",  # table_name
                    "amount_due",  # column_name
                    None,  # metric_id
                    None,  # relationship_name
                    None,  # from_schema
                    None,  # from_table
                    None,  # from_columns
                    None,  # to_schema
                    None,  # to_table
                    None,  # to_columns
                )
            ],
        )

    def test_run_upserts_root_and_writes_memory_tables(self):
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    memories:
                      - memory_id: ticket_assignee_join
                        memory_kind: join_rule
                        content: Join ticket.assignee_id to user.id.
                        anchors:
                          - anchor_id: ticket_to_user
                            anchor_type: relationship
                            from_schema: zendesk
                            from_table: ticket
                            from_columns: [assignee_id]
                            to_schema: zendesk
                            to_table: user
                            to_columns: [id]
                    """
                )
            )
            cfg = {"metadata_connection": {"path": str(path)}}

            with (
                patch("agents_schema.memory.open_destination", return_value=DestinationContext(dest)),
                patch("builtins.print"),
            ):
                memory.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"memory"})
        self.assertEqual([call[0] for call in dest.calls[1:3]], ["replace", "replace"])
        self.assertEqual(dest.calls[3][1], "agents.memory")
        self.assertEqual(dest.calls[4][1], "agents.memory_anchor")


if __name__ == "__main__":
    unittest.main()
