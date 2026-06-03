import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import metadata_connectors


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


FIXTURE = {
    "workspaces": [
        {
            "id": "workspace-1",
            "name": "Finance",
            "datasets": [
                {
                    "id": "model-1",
                    "name": "Finance Model",
                    "tables": [
                        {
                            "name": "Revenue",
                            "columns": [{"name": "amount", "dataType": "decimal"}],
                            "measures": [{"name": "MRR", "expression": "SUM(Revenue[amount])"}],
                        }
                    ],
                }
            ],
            "reports": [{"id": "report-1", "name": "Executive MRR", "datasetId": "model-1"}],
        }
    ]
}


class MetadataConnectorTests(unittest.TestCase):
    def test_powerbi_connector_writes_root_and_source_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "powerbi.json"
            path.write_text(json.dumps(FIXTURE))
            dest = FakeDestination()

            with (
                patch("agents_schema.metadata_helpers.open_destination", return_value=DestinationContext(dest)),
                patch("builtins.print"),
            ):
                metadata_connectors.run("powerbi", {"metadata_connection": {"path": str(path)}})

            self.assertEqual(dest.calls[0][0], "upsert")
            self.assertEqual({row[0] for row in dest.calls[0][2]}, {"powerbi"})
            replaced_tables = {call[1] for call in dest.calls if call[0] == "replace"}
            self.assertIn("agents.powerbi_workspace", replaced_tables)
            self.assertIn("agents.powerbi_measure", replaced_tables)
            inserted = [call for call in dest.calls if call[0] == "insert"]
            self.assertTrue(inserted)
            self.assertTrue(any(call[2] for call in inserted))


if __name__ == "__main__":
    unittest.main()
