import unittest

from agents_schema.metadata_connectors import SUPPORTED_PROVIDERS
from agents_schema.root import ROOT, upsert_provider_root


class FakeDestination:
    def __init__(self):
        self.upserts = []

    def upsert_rows(self, table, rows):
        self.upserts.append((table, list(rows)))


class RootTests(unittest.TestCase):
    def test_upsert_provider_root_writes_only_requested_provider(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "dbt")

        self.assertEqual(len(dest.upserts), 1)
        table, rows = dest.upserts[0]
        self.assertIs(table, ROOT)
        self.assertTrue(rows)
        self.assertEqual({row[0] for row in rows}, {"dbt"})
        self.assertEqual({row[1] for row in rows}, {"overview", "model", "column", "dependency"})

    def test_upsert_provider_root_has_osi_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "osi")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "dataset", "field", "metric", "relationship"})

    def test_all_metadata_connectors_publish_root_entries(self):
        for provider in SUPPORTED_PROVIDERS:
            with self.subTest(provider=provider):
                dest = FakeDestination()

                upsert_provider_root(dest, provider)

                _, rows = dest.upserts[0]
                self.assertTrue(rows)
                self.assertEqual({row[0] for row in rows}, {provider})
                self.assertIn("overview", {row[1] for row in rows})


if __name__ == "__main__":
    unittest.main()
