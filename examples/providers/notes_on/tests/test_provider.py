import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agents_schema_notes_on import provider
from agents_schema_notes_on.cli import main
from agents_schema_notes_on.provider import NotesOnError


class FakeDestination:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))


class NotesOnProviderTests(unittest.TestCase):
    def test_load_notes_file_returns_schema_table_and_column_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    schema_notes:
                      - note_id: sales_schema_time_policy
                        schema_name: sales
                        kind: time_policy
                        tags: [finance, revenue]
                        content: Use closed_at unless the question asks about pipeline creation.
                        confidence: 0.95
                        importance: 0.8
                    table_notes:
                      - note_id: zendesk_ticket_grain
                        table_schema: zendesk
                        table_name: ticket
                        kind: grain_warning
                        content: One row is one current ticket.
                    column_notes:
                      - note_id: stripe_invoice_amount_due_cents
                        table_schema: stripe
                        table_name: invoice
                        column_name: amount_due
                        kind: unit_rule
                        tags: [stripe, money]
                        content: Stripe amount columns are stored in cents.
                    """
                )
            )

            schema_rows, table_rows, column_rows = provider.load_notes_file(path)

        self.assertEqual(schema_rows[0][:6], (
            "sales_schema_time_policy",
            "sales",
            "time_policy",
            ["finance", "revenue"],
            None,
            "Use closed_at unless the question asks about pipeline creation.",
        ))
        self.assertEqual(table_rows[0][:6], (
            "zendesk_ticket_grain",
            None,
            "zendesk",
            "ticket",
            "grain_warning",
            None,
        ))
        self.assertEqual(column_rows[0][:7], (
            "stripe_invoice_amount_due_cents",
            None,
            "stripe",
            "invoice",
            "amount_due",
            "unit_rule",
            ["stripe", "money"],
        ))

    def test_load_notes_file_rejects_duplicate_note_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    table_notes:
                      - note_id: duplicate
                        table_schema: zendesk
                        table_name: ticket
                        kind: grain_warning
                        content: Table note.
                    column_notes:
                      - note_id: duplicate
                        table_schema: zendesk
                        table_name: ticket
                        column_name: status
                        kind: status_mapping
                        content: Column note.
                    """
                )
            )

            with self.assertRaisesRegex(NotesOnError, "duplicate note_id: duplicate"):
                provider.load_notes_file(path)

    def test_load_notes_file_rejects_bad_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    schema_notes:
                      - note_id: bad_tags
                        schema_name: sales
                        kind: time_policy
                        tags: [finance, 123]
                        content: Use closed_at.
                    """
                )
            )

            with self.assertRaisesRegex(NotesOnError, "schema_notes\\[0\\]\\.tags must be a list of strings"):
                provider.load_notes_file(path)

    def test_load_notes_file_rejects_bad_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    table_notes:
                      - note_id: bad_confidence
                        table_schema: zendesk
                        table_name: ticket
                        kind: grain_warning
                        content: Table note.
                        confidence: 2.0
                    """
                )
            )

            with self.assertRaisesRegex(NotesOnError, "table_notes\\[0\\]\\.confidence must be between 0 and 1"):
                provider.load_notes_file(path)

    def test_run_writes_root_and_note_tables(self):
        dest = FakeDestination()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("agents_schema_notes_on.provider.SnowflakeDestination.from_env", return_value=dest),
            redirect_stdout(StringIO()),
        ):
            path = Path(tmp) / "notes.yml"
            path.write_text(
                textwrap.dedent(
                    """
                    column_notes:
                      - note_id: stripe_invoice_amount_due_cents
                        table_schema: stripe
                        table_name: invoice
                        column_name: amount_due
                        kind: unit_rule
                        content: Stripe amount columns are stored in cents.
                    """
                )
            )

            provider.run(path)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual(dest.calls[0][1], "root")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"notes_on"})
        self.assertIn(
            (
                "notes_on",
                "schemata",
                "One row per note attached to a warehouse schema. See AGENTS.NOTES_ON_SCHEMATA.",
            ),
            dest.calls[0][2],
        )
        self.assertEqual([call[0] for call in dest.calls[1:4]], ["replace", "replace", "replace"])
        self.assertEqual(dest.calls[1][1], "notes_on_schemata")
        self.assertEqual(dest.calls[4][0], "insert")
        self.assertEqual(dest.calls[4][1], "notes_on_columns")

    def test_cli_returns_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.yml"
            path.write_text("column_notes: {}\n")

            with redirect_stderr(StringIO()):
                status = main(["--notes-file", str(path)])

        self.assertEqual(status, 1)

    def test_variant_values_are_bound_as_json(self):
        rows = provider._bind_rows(provider.NOTES_ON_COLUMNS, [(
            "stripe_invoice_amount_due_cents",
            None,
            "stripe",
            "invoice",
            "amount_due",
            "unit_rule",
            ["stripe", "money"],
            None,
            "Stripe amount columns are stored in cents.",
            None,
            None,
            0.9,
            1.0,
            None,
            None,
        )])

        self.assertEqual(rows[0][6], '["stripe", "money"]')
        self.assertIn("PARSE_JSON(%s)", provider._insert_sql(provider.NOTES_ON_COLUMNS, 1))

    def test_warehouse_credentials_from_env_accepts_yaml(self):
        with patch.dict(
            os.environ,
            {
                "WAREHOUSE_CREDENTIALS": textwrap.dedent(
                    """
                    type: snowflake
                    account: example
                    user: service_user
                    warehouse: transform_wh
                    database: analytics
                    password: secret
                    """
                )
            },
        ):
            creds = provider.warehouse_credentials_from_env()

        self.assertEqual(creds["type"], "snowflake")
        self.assertEqual(creds["database"], "analytics")


if __name__ == "__main__":
    unittest.main()
