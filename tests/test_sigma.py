import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import cli
from agents_schema.sigma import (
    SIGMA_COLUMN,
    SIGMA_DATA_MODEL,
    SIGMA_ELEMENT,
    SIGMA_METRIC,
    _col_display_name,
    _ingest,
    _is_simple_metric,
    _load_sigma_files,
    _source_path,
)

_FIXTURE_YAML = """\
dataModelId: abc123
name: Sales Data Model
description: Revenue and pipeline metrics
schemaVersion: 1
pages:
  - id: page1
    name: Revenue
    elements:
      - id: elem1
        kind: table
        source:
          connectionId: conn-abc
          kind: warehouse-table
          path:
            - ANALYTICS
            - REVENUE
            - ORDERS
        columns:
          - id: col1
            formula: '[ORDERS/Order Id]'
            name: Order ID
            description: Unique order identifier
          - id: col2
            formula: '[ORDERS/Amount]'
            name: Amount
          - id: col3_computed
            formula: 'DateTrunc("day", [ORDERS/Created At])'
            name: Order Date (Truncated)
          - id: col4_computed
            formula: 'If([ORDERS/Status] = "Active", 1, 0)'
            name: Is Active Flag
          - id: col5_computed
            formula: '[Active Order Count (Source Table)]'
            name: Active Order Count
          - id: col6_computed
            formula: '[ORDERS/Amount] / [ORDERS/Quantity]'
            name: Unit Price
        name: Orders
        metrics:
          - id: met1
            formula: Sum([ORDERS/Amount])
            name: Total Revenue
            description: Sum of all order amounts
          - id: met2
            formula: CountDistinct([ORDERS/Order Id])
            name: Order Count
          - id: met3
            formula: 'SumIf([ORDERS/Amount], [ORDERS/Is Returned])'
            name: Returned Revenue
          - id: met4
            formula: '[Metrics/Total Revenue] / [Metrics/Order Count]'
            name: Avg Order Value
          - id: met5
            formula: 'CountDistinctIf([ORDERS/Order Id], DateDiff("day", [ORDERS/Created At], Today()) < 30)'
            name: Orders Last 30 Days
          - id: met6
            formula: 'PercentileCont([ORDERS/Amount], 0.9)'
            name: P90 Order Value
          - id: met7
            formula: 'Sum([ORDERS/Quantity] * [ORDERS/Price])'
            name: Computed Revenue
          - id: met8
            formula: 'Count()'
            name: Row Count
          - id: met9
            formula: 'CountIf([ORDERS/Is Active])'
            name: Active Orders
  - id: page2
    name: Pipeline
    elements:
      - id: elem2
        kind: table
        source:
          connectionId: conn-abc
          kind: warehouse-table
          path:
            - ANALYTICS
            - PIPELINE
            - OPPORTUNITIES
        columns:
          - id: col_opp1
            formula: '[OPPORTUNITIES/Opp Id]'
            name: Opportunity ID
          - id: col_opp2_computed
            formula: 'Sum([OPPORTUNITIES/Opp Value])'
            name: Total Opportunity Value
        name: Opportunities
      - kind: control
        controlId: Start-Time
        id: ctrl1
"""

_FIXTURE_NO_TABLES_YAML = """\
dataModelId: xyz999
name: Controls Only
schemaVersion: 1
pages:
  - id: page1
    name: Filters
    elements:
      - kind: control
        controlId: Date-Range
        id: ctrl1
"""

_ORDERS_PATH = "ANALYTICS.REVENUE.ORDERS"
_OPPS_PATH = "ANALYTICS.PIPELINE.OPPORTUNITIES"


class FakeDestination:
    def __init__(self):
        self.calls = []

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name, list(rows)))

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name, list(rows)))


class DestinationContext:
    def __init__(self, dest):
        self.dest = dest

    def __enter__(self):
        return self.dest

    def __exit__(self, exc_type, exc, tb):
        return None


def _write_fixture(tmp_dir: Path, content: str = _FIXTURE_YAML, name: str = "model.sigma.yaml") -> tuple[list[Path], Path]:
    f = tmp_dir / name
    f.write_text(content)
    return [f], tmp_dir


class ColDisplayNameTests(unittest.TestCase):
    def test_returns_explicit_name(self):
        self.assertEqual(_col_display_name({"name": "Order ID", "formula": "[T/x]"}), "Order ID")

    def test_extracts_name_from_direct_formula(self):
        self.assertEqual(_col_display_name({"formula": "[ORDERS/Order Number]"}), "Order Number")

    def test_extracts_inode_formula_column_part(self):
        self.assertEqual(
            _col_display_name({"formula": "[inode-abc123/REVENUE_AMOUNT]"}), "REVENUE_AMOUNT"
        )

    def test_returns_none_for_computed_formula_without_name(self):
        self.assertIsNone(_col_display_name({"formula": 'DateTrunc("day", [T/c])'}))

    def test_returns_none_for_empty(self):
        self.assertIsNone(_col_display_name({}))


class SimpleMetricTests(unittest.TestCase):
    def test_accepts_sum(self):
        self.assertTrue(_is_simple_metric("Sum([ORDERS/Amount])"))

    def test_accepts_avg(self):
        self.assertTrue(_is_simple_metric("Avg([ORDERS/Amount])"))

    def test_accepts_count(self):
        self.assertTrue(_is_simple_metric("Count([ORDERS/Order Id])"))

    def test_accepts_count_distinct(self):
        self.assertTrue(_is_simple_metric("CountDistinct([ORDERS/Order Id])"))

    def test_accepts_min(self):
        self.assertTrue(_is_simple_metric("Min([ORDERS/Created At])"))

    def test_accepts_max(self):
        self.assertTrue(_is_simple_metric("Max([ORDERS/Created At])"))

    def test_accepts_field_with_spaces(self):
        self.assertTrue(_is_simple_metric("Sum([ORDERS/Revenue Amount])"))

    def test_accepts_field_with_slash(self):
        self.assertTrue(_is_simple_metric("CountDistinct([APP_CS_COE__ACCOUNTS/Account Guid])"))

    def test_rejects_conditional_sumif(self):
        self.assertFalse(_is_simple_metric("SumIf([ORDERS/Amount], [ORDERS/Is Returned])"))

    def test_rejects_conditional_countif(self):
        self.assertFalse(_is_simple_metric("CountIf([ORDERS/Is Active])"))

    def test_rejects_conditional_count_distinct_if(self):
        self.assertFalse(
            _is_simple_metric(
                'CountDistinctIf([ORDERS/Order Id], DateDiff("day", [ORDERS/Created At], Today()) < 30)'
            )
        )

    def test_rejects_cross_metric_reference(self):
        self.assertFalse(_is_simple_metric("[Metrics/Revenue] / [Metrics/Total COGS]"))

    def test_rejects_cross_metric_subtraction(self):
        self.assertFalse(_is_simple_metric("[Metrics/Revenue] - [Metrics/Total COGS]"))

    def test_rejects_cross_metric_division(self):
        self.assertFalse(_is_simple_metric("[Metrics/Profit] / [Metrics/Distinct Customers]"))

    def test_rejects_multi_field_multiplication(self):
        self.assertFalse(_is_simple_metric("Sum([ORDERS/Quantity] * [ORDERS/Price])"))

    def test_rejects_parenthesized_multi_field(self):
        self.assertFalse(_is_simple_metric("(Sum([Sales Quantity] * [Price]))"))

    def test_rejects_percentile_function(self):
        self.assertFalse(_is_simple_metric("PercentileCont([ORDERS/Amount], 0.9)"))

    def test_rejects_no_argument_count(self):
        self.assertFalse(_is_simple_metric("Count()"))

    def test_rejects_unknown_function(self):
        self.assertFalse(_is_simple_metric("Median([ORDERS/Amount])"))

    def test_rejects_empty_string(self):
        self.assertFalse(_is_simple_metric(""))

    def test_rejects_count_distinct_if_with_boolean_logic(self):
        self.assertFalse(
            _is_simple_metric(
                "CountDistinctIf([User Uuid], ([Used Advanced] or [Used Enhanced]) and [Is Active User Last 90 Days])"
            )
        )


class SourcePathTests(unittest.TestCase):
    def test_joins_path_components(self):
        source = {"path": ["ANALYTICS", "REVENUE", "ORDERS"]}
        self.assertEqual(_source_path(source), "ANALYTICS.REVENUE.ORDERS")

    def test_returns_none_for_missing_source(self):
        self.assertIsNone(_source_path(None))

    def test_returns_none_for_empty_path(self):
        self.assertIsNone(_source_path({"path": []}))

    def test_returns_none_for_absent_path_key(self):
        self.assertIsNone(_source_path({"connectionId": "abc"}))

    def test_returns_none_for_non_list_path(self):
        self.assertIsNone(_source_path({"path": "DB.SCHEMA.TABLE"}))

    def test_returns_none_for_non_dict_source(self):
        self.assertIsNone(_source_path("warehouse-table"))


class LoadSigmaFilesTests(unittest.TestCase):
    def test_discovers_sigma_yaml_files_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "models"
            nested.mkdir()
            (root / "sales.sigma.yaml").write_text(_FIXTURE_YAML)
            (nested / "pipeline.sigma.yaml").write_text(_FIXTURE_YAML)

            files = _load_sigma_files(root)

        self.assertEqual(len(files), 2)

    def test_raises_when_no_sigma_yaml_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, r"no \*\.sigma\.yaml files"):
                _load_sigma_files(Path(tmp))

    def test_ignores_non_sigma_yaml_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.yaml").write_text("foo: bar")
            (root / "sales.sigma.yaml").write_text(_FIXTURE_YAML)

            files = _load_sigma_files(root)

        self.assertEqual(len(files), 1)


class IngestTests(unittest.TestCase):
    def _run(self, content: str = _FIXTURE_YAML):
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            files, sigma_dir = _write_fixture(Path(tmp), content)
            with patch("builtins.print"):
                _ingest(dest, files, sigma_dir)
        return dest

    def test_ingest_writes_data_model_row(self):
        dest = self._run()
        dm_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_DATA_MODEL.name)
        rows = dm_insert[2]
        self.assertEqual(len(rows), 1)
        source_file, name, description = rows[0]
        self.assertEqual(source_file, "model.sigma.yaml")
        self.assertEqual(name, "Sales Data Model")
        self.assertEqual(description, "Revenue and pipeline metrics")

    def test_ingest_extracts_table_elements(self):
        dest = self._run()
        element_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_ELEMENT.name)
        rows = element_insert[2]
        self.assertEqual(len(rows), 2)
        src_paths = {r[0] for r in rows}
        self.assertIn(_ORDERS_PATH, src_paths)
        self.assertIn(_OPPS_PATH, src_paths)

    def test_ingest_skips_control_elements(self):
        dest = self._run()
        element_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_ELEMENT.name)
        src_paths = {r[0] for r in element_insert[2]}
        self.assertNotIn("ctrl1", src_paths)

    def test_ingest_element_row_has_correct_fields(self):
        dest = self._run()
        element_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_ELEMENT.name)
        orders_row = next(r for r in element_insert[2] if r[0] == _ORDERS_PATH)
        source_path, source_file, page_name, element_name, connection_id, description = orders_row
        self.assertEqual(source_path, _ORDERS_PATH)
        self.assertEqual(source_file, "model.sigma.yaml")
        self.assertEqual(page_name, "Revenue")
        self.assertEqual(element_name, "Orders")
        self.assertEqual(connection_id, "conn-abc")

    def test_ingest_extracts_columns_with_kind(self):
        dest = self._run()
        col_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_COLUMN.name)
        rows = col_insert[2]
        by_name = {r[1]: r for r in rows}

        expected_keys = {
            (_ORDERS_PATH, "Order ID"),
            (_ORDERS_PATH, "Amount"),
            (_ORDERS_PATH, "Order Date (Truncated)"),
            (_ORDERS_PATH, "Is Active Flag"),
            (_ORDERS_PATH, "Active Order Count"),
            (_ORDERS_PATH, "Unit Price"),
            (_OPPS_PATH, "Opportunity ID"),
            (_OPPS_PATH, "Total Opportunity Value"),
        }
        self.assertEqual({(r[0], r[1]) for r in rows}, expected_keys)

        # direct: bare [TABLE/Col] formula
        self.assertEqual(by_name["Order ID"][2], "direct")
        self.assertEqual(by_name["Amount"][2], "direct")
        self.assertEqual(by_name["Opportunity ID"][2], "direct")

        # computed: any other formula
        self.assertEqual(by_name["Order Date (Truncated)"][2], "computed")
        self.assertEqual(by_name["Is Active Flag"][2], "computed")
        self.assertEqual(by_name["Active Order Count"][2], "computed")
        self.assertEqual(by_name["Unit Price"][2], "computed")
        self.assertEqual(by_name["Total Opportunity Value"][2], "computed")

        order_id_row = by_name["Order ID"]
        self.assertEqual(order_id_row[0], _ORDERS_PATH)
        self.assertEqual(order_id_row[3], "[ORDERS/Order Id]")
        self.assertEqual(order_id_row[4], "Unique order identifier")

    def test_ingest_includes_only_simple_metrics(self):
        dest = self._run()
        metric_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name)
        rows = metric_insert[2]
        names = {r[1] for r in rows}

        self.assertIn("Total Revenue", names)
        self.assertIn("Order Count", names)
        self.assertNotIn("Returned Revenue", names)
        self.assertNotIn("Avg Order Value", names)
        self.assertNotIn("Orders Last 30 Days", names)
        self.assertNotIn("P90 Order Value", names)
        self.assertNotIn("Computed Revenue", names)
        self.assertNotIn("Row Count", names)
        self.assertNotIn("Active Orders", names)

    def test_ingest_metric_row_has_correct_fields(self):
        dest = self._run()
        metric_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name)
        met1 = next(r for r in metric_insert[2] if r[1] == "Total Revenue")
        self.assertEqual(met1[0], _ORDERS_PATH)
        self.assertEqual(met1[2], "Sum([ORDERS/Amount])")
        self.assertEqual(met1[3], "Sum of all order amounts")

    def test_ingest_raises_on_empty_file(self):
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            sigma_dir = Path(tmp)
            (sigma_dir / "empty.sigma.yaml").write_text("")
            files = [sigma_dir / "empty.sigma.yaml"]
            with self.assertRaises(ValueError, msg="expected a YAML mapping"):
                with patch("builtins.print"):
                    _ingest(dest, files, sigma_dir)

    def test_ingest_raises_on_scalar_yaml_file(self):
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            sigma_dir = Path(tmp)
            (sigma_dir / "scalar.sigma.yaml").write_text("just a string\n")
            files = [sigma_dir / "scalar.sigma.yaml"]
            with self.assertRaises(ValueError, msg="expected a YAML mapping"):
                with patch("builtins.print"):
                    _ingest(dest, files, sigma_dir)

    def test_ingest_model_without_pages_writes_only_data_model_row(self):
        yaml = """\
dataModelId: m1
name: No Pages Model
schemaVersion: 1
"""
        dest = self._run(yaml)
        dm_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_DATA_MODEL.name)
        self.assertEqual(len(dm_insert[2]), 1)
        inserted = {c[1] for c in dest.calls if c[0] == "insert"}
        self.assertNotIn(SIGMA_ELEMENT.name, inserted)
        self.assertNotIn(SIGMA_COLUMN.name, inserted)
        self.assertNotIn(SIGMA_METRIC.name, inserted)

    def test_ingest_element_without_source_is_skipped(self):
        yaml = """\
dataModelId: m1
name: Model
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        name: Sourceless Element
"""
        dest = self._run(yaml)
        inserted = {c[1] for c in dest.calls if c[0] == "insert"}
        self.assertNotIn(SIGMA_ELEMENT.name, inserted)

    def test_ingest_metric_with_simple_formula_but_no_name_is_dropped(self):
        yaml = """\
dataModelId: m1
name: Model
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        name: Table
        columns:
          - id: c1
            formula: '[TABLE/Col]'
            name: Col
        metrics:
          - id: x1
            formula: 'Sum([TABLE/Amount])'
"""
        dest = self._run(yaml)
        metric_inserts = [c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name]
        self.assertEqual(metric_inserts, [])

    def test_ingest_no_elements_skips_element_column_metric_inserts(self):
        dest = self._run(_FIXTURE_NO_TABLES_YAML)
        table_names = {c[1] for c in dest.calls if c[0] == "insert"}
        self.assertNotIn(SIGMA_ELEMENT.name, table_names)
        self.assertNotIn(SIGMA_COLUMN.name, table_names)
        self.assertNotIn(SIGMA_METRIC.name, table_names)

    def test_ingest_no_elements_still_writes_data_model(self):
        dest = self._run(_FIXTURE_NO_TABLES_YAML)
        dm_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_DATA_MODEL.name)
        self.assertEqual(len(dm_insert[2]), 1)

    def test_ingest_prints_summary(self):
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            files, sigma_dir = _write_fixture(Path(tmp))
            with patch("builtins.print") as mock_print:
                _ingest(dest, files, sigma_dir)
        output = mock_print.call_args[0][0]
        self.assertIn("sigma:", output)
        self.assertIn("1 data model", output)
        self.assertIn("2 elements", output)
        self.assertIn("8 columns", output)
        self.assertIn("2 metrics", output)

    def test_ingest_column_without_formula_stores_none_and_kind_computed(self):
        yaml = """\
dataModelId: m1
name: Model
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        name: Table
        columns:
          - id: c1
            name: Label Column
"""
        dest = self._run(yaml)
        col_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_COLUMN.name)
        _src, name, kind, formula, _desc = col_insert[2][0]
        self.assertEqual(name, "Label Column")
        self.assertEqual(kind, "computed")
        self.assertIsNone(formula)

    def test_ingest_metric_without_formula_is_dropped(self):
        yaml = """\
dataModelId: m1
name: Model
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        name: Table
        columns:
          - id: c1
            formula: '[TABLE/Col]'
            name: Col
        metrics:
          - id: x1
            name: Formulaless Metric
"""
        dest = self._run(yaml)
        metric_inserts = [c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name]
        self.assertEqual(metric_inserts, [])

    def test_ingest_all_complex_metrics_dropped_produces_no_metric_insert(self):
        only_complex_yaml = """\
dataModelId: m1
name: Complex Only
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        columns:
          - id: c1
            formula: '[TABLE/Col]'
            name: Col
        name: Table
        metrics:
          - id: x1
            formula: 'SumIf([TABLE/Amount], [TABLE/Flag])'
            name: Conditional Sum
          - id: x2
            formula: '[Metrics/A] / [Metrics/B]'
            name: Ratio
"""
        dest = self._run(only_complex_yaml)
        metric_inserts = [c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name]
        self.assertEqual(metric_inserts, [])

    def test_ingest_first_file_wins_for_duplicate_source_path(self):
        yaml_a = """\
dataModelId: m1
name: Model A
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e1
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        columns:
          - id: c1
            formula: '[TABLE/Revenue]'
            name: Revenue
        name: Table
        metrics:
          - id: x1
            formula: 'Sum([TABLE/Revenue])'
            name: Total Revenue
"""
        yaml_b = """\
dataModelId: m2
name: Model B
schemaVersion: 1
pages:
  - id: p1
    name: Page
    elements:
      - id: e2
        kind: table
        source:
          connectionId: conn
          kind: warehouse-table
          path: [DB, SCHEMA, TABLE]
        columns:
          - id: c2
            formula: '[TABLE/Revenue]'
            name: Revenue
          - id: c3
            formula: '[TABLE/Units]'
            name: Units
        name: Table
        metrics:
          - id: x2
            formula: 'Sum([TABLE/Revenue])'
            name: Total Revenue
          - id: x3
            formula: 'Sum([TABLE/Units])'
            name: Total Units
"""
        dest = FakeDestination()
        with tempfile.TemporaryDirectory() as tmp:
            sigma_dir = Path(tmp)
            (sigma_dir / "a.sigma.yaml").write_text(yaml_a)
            (sigma_dir / "b.sigma.yaml").write_text(yaml_b)
            files = _load_sigma_files(sigma_dir)
            with patch("builtins.print"):
                _ingest(dest, files, sigma_dir)

        # Both data model rows are always written
        dm_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_DATA_MODEL.name)
        self.assertEqual(len(dm_insert[2]), 2)

        # Only one element row (first file wins)
        elem_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_ELEMENT.name)
        self.assertEqual(len(elem_insert[2]), 1)
        self.assertEqual(elem_insert[2][0][1], "a.sigma.yaml")

        # Columns and metrics from the second file's duplicate element are excluded
        col_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_COLUMN.name)
        col_names = {r[1] for r in col_insert[2]}
        self.assertIn("Revenue", col_names)
        self.assertNotIn("Units", col_names)

        metric_insert = next(c for c in dest.calls if c[0] == "insert" and c[1] == SIGMA_METRIC.name)
        metric_names = {r[1] for r in metric_insert[2]}
        self.assertIn("Total Revenue", metric_names)
        self.assertNotIn("Total Units", metric_names)


class CliTests(unittest.TestCase):
    def test_cli_dispatches_sigma(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.sigma.run") as run,
        ):
            result = cli.main(["sigma", "--sigma-dir", "sigma"])

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            {
                "warehouse": {"type": "snowflake"},
                "metadata_connection": {
                    "type": "sigma",
                    "path": "sigma",
                },
            }
        )

    def test_cli_sigma_requires_sigma_dir(self):
        with patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"):
            with self.assertRaises(SystemExit):
                cli.main(["sigma"])

    def test_cli_sigma_returns_1_on_missing_dir(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.sigma.run", side_effect=FileNotFoundError("no *.sigma.yaml")),
        ):
            result = cli.main(["sigma", "--sigma-dir", "nonexistent"])

        self.assertEqual(result, 1)

    def test_cli_sigma_returns_1_on_malformed_yaml(self):
        with (
            patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
            patch("agents_schema.cli.sigma.run", side_effect=ValueError("empty.sigma.yaml: expected a YAML mapping, got NoneType")),
        ):
            result = cli.main(["sigma", "--sigma-dir", "sigma"])

        self.assertEqual(result, 1)


class SigmaRunConnectorTests(unittest.TestCase):
    def test_run_upserts_root_before_source_tables(self):
        dest = FakeDestination()

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "model.sigma.yaml").write_text(_FIXTURE_YAML)
            cfg = {"metadata_connection": {"path": tmp}}
            with (
                patch("agents_schema.sigma.open_destination", return_value=DestinationContext(dest)),
                patch("builtins.print"),
            ):
                from agents_schema import sigma as sigma_mod
                sigma_mod.run(cfg)

        self.assertEqual(dest.calls[0][0], "upsert")
        self.assertEqual({row[0] for row in dest.calls[0][2]}, {"sigma"})
        self.assertEqual([call[0] for call in dest.calls[1:5]], ["replace", "replace", "replace", "replace"])


if __name__ == "__main__":
    unittest.main()
