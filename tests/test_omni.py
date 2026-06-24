import tempfile
import unittest
from pathlib import Path

from agents_schema.omni import (
    _collect_joins,
    _topic_name_from_file,
    _view_name_from_file,
    _ingest,
    OMNI_VIEW,
    OMNI_DIMENSION,
    OMNI_MEASURE,
    OMNI_TOPIC,
    OMNI_TOPIC_JOIN,
)


class FakeDestination:
    def __init__(self):
        self.calls = []

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))


VIEW_YAML = """\
# Reference this view as schema_a__view_foo
schema: schema_a
table_name: VIEW_FOO
label: Foo View
description: A test view.

dimensions:
  record_id:
    sql: '"RECORD_ID"'
    description: The record identifier.
    format: ID
    primary_key: true
  title:
    sql: '"TITLE"'
    label: Record Title

measures:
  count:
    aggregate_type: count
  total_value:
    aggregate_type: sum
    sql: '"VALUE"'
    description: Sum of values.
"""

VIEW_YAML_NO_COMMENT = """\
schema: schema_b
table_name: VIEW_BAR
dimensions:
  id:
    sql: '"ID"'
"""

TOPIC_YAML = """\
base_view: schema_a__fact_alpha
base_view_label: Alpha
label: Alpha Topic
group_label: Group One
description: Alpha topic data.
ai_context: Use for alpha analysis.

joins:
  schema_a__dim_beta: {}
  schema_a__dim_gamma:
    schema_a__dim_delta: {}

views:
  schema_a__fact_alpha:
    display_order: 0
  schema_a__dim_beta:
    display_order: 1
"""

TOPIC_YAML_NO_JOINS = """\
base_view: schema_a__fact_epsilon
label: Epsilon
joins: {}
"""


class ViewNameTests(unittest.TestCase):
    def test_view_name_from_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = base / "view_foo.view.yaml"
            p.write_text(VIEW_YAML)
            self.assertEqual(_view_name_from_file(p, base), "schema_a__view_foo")

    def test_view_name_fallback_with_schema_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            schema_dir = base / "omni_dbt"
            schema_dir.mkdir()
            p = schema_dir / "stg_foo.view.yaml"
            p.write_text(VIEW_YAML_NO_COMMENT)
            self.assertEqual(_view_name_from_file(p, base), "omni_dbt__stg_foo")

    def test_view_name_fallback_at_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = base / "stg_foo.view.yaml"
            p.write_text(VIEW_YAML_NO_COMMENT)
            self.assertEqual(_view_name_from_file(p, base), "stg_foo")


class TopicNameTests(unittest.TestCase):
    def test_topic_name_strips_suffix(self):
        p = Path("omni_dbt__fct_orders.topic.yaml")
        self.assertEqual(_topic_name_from_file(p), "omni_dbt__fct_orders")

    def test_topic_name_with_spaces(self):
        p = Path("Exec MBR Metrics: FY27 (Quarter).topic.yaml")
        self.assertEqual(_topic_name_from_file(p), "Exec MBR Metrics: FY27 (Quarter)")


class CollectJoinsTests(unittest.TestCase):
    def test_direct_joins(self):
        joins = {"view_b": {}, "view_c": {}}
        seen, result = set(), []
        _collect_joins(joins, "view_a", seen, result)
        self.assertIn(("view_a", "view_b"), result)
        self.assertIn(("view_a", "view_c"), result)

    def test_nested_joins(self):
        joins = {"view_b": {"view_c": {}}}
        seen, result = set(), []
        _collect_joins(joins, "view_a", seen, result)
        self.assertEqual(result, [("view_a", "view_b"), ("view_b", "view_c")])

    def test_deeply_nested_joins(self):
        joins = {"view_b": {"view_c": {"view_d": {}}}}
        seen, result = set(), []
        _collect_joins(joins, "view_a", seen, result)
        self.assertEqual(result, [
            ("view_a", "view_b"),
            ("view_b", "view_c"),
            ("view_c", "view_d"),
        ])

    def test_no_duplicate_edges(self):
        joins = {"view_b": {}, "view_c": {}}
        seen = {("view_a", "view_b")}
        result = []
        _collect_joins(joins, "view_a", seen, result)
        self.assertEqual(result, [("view_a", "view_c")])

    def test_empty_joins(self):
        seen, result = set(), []
        _collect_joins({}, "view_a", seen, result)
        self.assertEqual(result, [])


class IngestTests(unittest.TestCase):
    def _write_files(self, tmp):
        base = Path(tmp)
        (base / "view_foo.view.yaml").write_text(VIEW_YAML)
        (base / "alpha.topic.yaml").write_text(TOPIC_YAML)
        (base / "epsilon.topic.yaml").write_text(TOPIC_YAML_NO_JOINS)
        return base

    def _inserted(self, dest, table_name):
        return next(
            (rows for op, name, rows in dest.calls if op == "insert" and name == table_name),
            None,
        )

    def test_view_row_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_VIEW.name)
            self.assertIsNotNone(rows)
            row = rows[0]
            self.assertEqual(row[0], "schema_a__view_foo")  # view_name
            self.assertEqual(row[1], "schema_a")            # schema
            self.assertEqual(row[2], "VIEW_FOO")            # table_name
            self.assertEqual(row[3], "Foo View")            # label
            self.assertIn("test view", row[4])              # description

    def test_dimension_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_DIMENSION.name)
            self.assertIsNotNone(rows)
            by_name = {r[1]: r for r in rows}
            self.assertIn("record_id", by_name)
            self.assertIn("title", by_name)
            rec = by_name["record_id"]
            self.assertEqual(rec[0], "schema_a__view_foo")  # view_name
            self.assertEqual(rec[4], "ID")                  # format
            self.assertTrue(rec[6])                         # primary_key

    def test_measure_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_MEASURE.name)
            self.assertIsNotNone(rows)
            by_name = {r[1]: r for r in rows}
            self.assertIn("count", by_name)
            self.assertIn("total_value", by_name)
            self.assertEqual(by_name["count"][3], "count")          # aggregate_type
            self.assertEqual(by_name["total_value"][5], "Sum of values.")  # description

    def test_topic_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_TOPIC.name)
            self.assertIsNotNone(rows)
            by_name = {r[0]: r for r in rows}
            self.assertIn("alpha", by_name)
            row = by_name["alpha"]
            self.assertEqual(row[1], "schema_a__fact_alpha")  # base_view
            self.assertEqual(row[2], "Alpha Topic")           # label
            self.assertEqual(row[3], "Group One")             # group_label
            self.assertEqual(row[5], "Use for alpha analysis.")  # ai_context

    def test_topic_join_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_TOPIC_JOIN.name)
            self.assertIsNotNone(rows)
            edges = {(r[1], r[2]) for r in rows if r[0] == "alpha"}
            self.assertIn(("schema_a__fact_alpha", "schema_a__dim_beta"), edges)
            self.assertIn(("schema_a__fact_alpha", "schema_a__dim_gamma"), edges)
            self.assertIn(("schema_a__dim_gamma", "schema_a__dim_delta"), edges)

    def test_empty_joins_produces_no_join_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = FakeDestination()
            _ingest(dest, self._write_files(tmp))
            rows = self._inserted(dest, OMNI_TOPIC_JOIN.name)
            epsilon_joins = [r for r in (rows or []) if r[0] == "epsilon"]
            self.assertEqual(epsilon_joins, [])


if __name__ == "__main__":
    unittest.main()
