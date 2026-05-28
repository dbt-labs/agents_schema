import unittest
from unittest.mock import patch

from agents_schema import dbt, lookml, osi


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


class ConnectorRootTests(unittest.TestCase):
    def test_dbt_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.dbt.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.dbt._load_manifest", return_value={"nodes": {}}),
            patch("builtins.print"),
        ):
            dbt.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"dbt"})
        self.assertEqual([call[0] for call in dest.calls[1:4]], ["replace", "replace", "replace"])

    def test_lookml_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.lookml.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.lookml._load_lookml_files", return_value=[]),
            patch("builtins.print"),
        ):
            lookml.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"lookml"})
        self.assertEqual([call[0] for call in dest.calls[1:5]], ["replace", "replace", "replace", "replace"])

    def test_osi_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()
        cfg = {"metadata_connection": {"path": "."}}

        with (
            patch("agents_schema.osi.open_destination", return_value=DestinationContext(dest)),
            patch("agents_schema.osi._load_osi_files", return_value=[]),
            patch("builtins.print"),
        ):
            osi.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"osi"})
        self.assertEqual([call[0] for call in dest.calls[1:5]], ["replace", "replace", "replace", "replace"])


if __name__ == "__main__":
    unittest.main()
