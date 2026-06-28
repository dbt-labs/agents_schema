"""Real-parser tests for the OSI connector — no mocked loader.

These exercise the actual `_load_osi_files` + `_ingest` against committed OSI
fixtures (the official OSI TPC-DS example), which is what proves the parser
matches the published spec. `FakeDestination` captures the raw row tuples
before any JSON encoding, so assertions read structured Python values.
"""
import unittest
from pathlib import Path

from agents_schema import osi

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURES_INVALID = Path(__file__).parent / "fixtures_invalid"


class FakeDestination:
    def __init__(self):
        self.tables = {}

    def replace_table(self, table):
        pass

    def insert_rows(self, table, rows):
        self.tables[table.name] = list(rows)


class OsiParserTests(unittest.TestCase):
    def setUp(self):
        self.dest = FakeDestination()
        osi._ingest(self.dest, osi._load_osi_files(FIXTURES))

    def rows(self, name):
        return self.dest.tables.get(name, [])

    def test_array_form_semantic_model_is_ingested(self):
        # The pre-fix parser read `semantic_model` as a dict and crashed on the
        # spec's array form. One model with many datasets/fields proves the fix.
        self.assertEqual(len(self.rows("agents.osi_model")), 1)
        self.assertGreater(len(self.rows("agents.osi_dataset")), 1)
        self.assertGreater(len(self.rows("agents.osi_field")), 1)

    def test_dataset_carries_model_name_and_source(self):
        ds = self.rows("agents.osi_dataset")[0]
        self.assertTrue(ds[0], "dataset row should carry its model_name")
        self.assertTrue(ds[2], "dataset row should carry its source")

    def test_multi_dialect_expressions_preserved(self):
        # OSI_FIELD.expressions is a list of {dialect, expression}, not a string.
        expr_lists = [r[5] for r in self.rows("agents.osi_field") if r[5]]
        self.assertTrue(expr_lists)
        first = expr_lists[0][0]
        self.assertIn("dialect", first)
        self.assertIn("expression", first)

    def test_synonyms_survive_structured_ai_context(self):
        synonyms = {s for r in self.rows("agents.osi_dataset") for s in r[6]}
        self.assertIn("sales transactions", synonyms)

    def test_malformed_model_raises(self):
        with self.assertRaises(ValueError):
            osi._load_osi_files(FIXTURES_INVALID)


if __name__ == "__main__":
    unittest.main()
