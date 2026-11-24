import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import lookml


class _Destination:
    def __init__(self):
        self.calls = []
        self.rows = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def upsert_rows(self, table, rows):
        self.calls.append(("upsert", table.name))

    def replace_table(self, table):
        self.calls.append(("replace", table.name))

    def insert_rows(self, table, rows):
        self.calls.append(("insert", table.name))
        self.rows[table.name.split(".")[-1]] = list(rows)

    def delete_rows(self, *args):
        self.calls.append(("delete",))


def _ingest(**files):
    """Write `files` (name -> text) and run the real parser; return the captured rows."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name, text in files.items():
            (base / f"{name}.lkml").write_text(text)
        dest = _Destination()
        with contextlib.redirect_stdout(open("/dev/null", "w")):
            lookml._ingest(dest, sorted(base.glob("*.lkml")), base)
    return dest.rows


def _by_name(rows, index=0):
    return {row[index]: row for row in rows}


class ViewPropertyTests(unittest.TestCase):
    def test_nested_blocks_do_not_overwrite_the_views_own_properties(self):
        rows = _ingest(
            orders="""
view: orders {
  sql_table_name: analytics.orders ;;
  label: "Orders"
  description: "One row per order."
  ai_context: "Use this for revenue."

  filter: status_filter {
    label: "Status Filter"
    description: "filter description"
  }
  parameter: currency {
    label: "Currency"
    description: "parameter description"
  }
  set: detail { fields: [id] }
  derived_table: {
    sql: SELECT * FROM raw.orders ;;
    description: "derived table description"
  }
  dimension: id { type: number }
}
"""
        )
        self.assertEqual(
            rows["LOOKML_VIEW"],
            [("orders", "analytics.orders", "Orders", "One row per order.", "Use this for revenue.", "orders.lkml")],
        )

    def test_quoted_values_can_span_several_lines(self):
        rows = _ingest(
            orders="""
view: orders {
  description: "One row per order.
    Includes cancelled orders."
  ai_context: "Prefer the signed-in
    customer grain."

  measure: total {
    type: sum
    sql: ${amount} ;;
    description: "Total order value
      in USD"
  }
}
"""
        )
        view = rows["LOOKML_VIEW"][0]
        self.assertEqual(view[3], "One row per order.\nIncludes cancelled orders.")
        self.assertEqual(view[4], "Prefer the signed-in\ncustomer grain.")
        self.assertEqual(rows["LOOKML_MEASURE"][0][4], "Total order value\nin USD")

    def test_braces_and_hashes_inside_strings_and_references_are_not_structure(self):
        rows = _ingest(
            orders="""
view: orders {
  description: "Uses {braces} and a # hash."
  dimension: link_text {
    type: string
    sql: ${TABLE}.name ;;
    html: <a href="{{ link }}">{{ value }}</a> ;;
    description: "{% if x %}conditional{% endif %}"
  }
  dimension: other { type: number }
}
"""
        )
        self.assertEqual(rows["LOOKML_VIEW"][0][3], "Uses {braces} and a # hash.")
        dims = _by_name(rows["LOOKML_DIMENSION"], 1)
        self.assertEqual(sorted(dims), ["link_text", "other"])
        self.assertEqual(dims["link_text"][4], "${TABLE}.name")

    def test_a_nested_block_inside_a_field_does_not_overwrite_the_fields_properties(self):
        rows = _ingest(
            orders="""
view: orders {
  dimension: id {
    type: number
    description: "The id"
    link: {
      label: "Open in admin"
      url: "https://example.com/{{ value }}"
    }
  }
}
"""
        )
        self.assertEqual(rows["LOOKML_DIMENSION"][0][5], "The id")

    def test_field_properties_are_parsed(self):
        rows = _ingest(
            orders="""
# a comment with view: fake { inside it
view: orders {
  dimension: id {
    primary_key: yes
    type: number
    sql: ${TABLE}.id ;;
  }
  dimension_group: created {
    type: time
    sql:
      ${TABLE}.created_at ;;
  }
  measure: completed {
    type: count
    filters: [status: "complete"]
  }
}
"""
        )
        dims = _by_name(rows["LOOKML_DIMENSION"], 1)
        self.assertEqual(dims["id"], ("orders", "id", "dimension", "number", "${TABLE}.id", None, None, True))
        self.assertEqual(dims["created"][2:5], ("dimension_group", "time", "${TABLE}.created_at"))
        self.assertFalse(dims["created"][7])
        self.assertEqual(rows["LOOKML_MEASURE"][0][2:], ("count", None, None, None, 'status: "complete"'))
        self.assertEqual([row[0] for row in rows["LOOKML_VIEW"]], ["orders"])


class RealWorldSyntaxTests(unittest.TestCase):
    """Constructs found in published LookML (Looker blocks, public projects) that line-based parsing got wrong."""

    def test_several_properties_on_one_line(self):
        rows = _ingest(
            orders="""
view: ga {
  dimension: deviceCategory { label:"Device Category" description:"mobile,tablet,desktop"}
  dimension: isMobile {type: yesno label: "Is Mobile" sql: ${deviceCategory} in ('mobile','tablet') ;; }
  dimension: id { primary_key: yes type: number sql: ${TABLE}.id ;; }
}
"""
        )
        dims = _by_name(rows["LOOKML_DIMENSION"], 1)
        self.assertEqual(dims["deviceCategory"][5], "mobile,tablet,desktop")
        self.assertEqual(dims["isMobile"][3:5], ("yesno", "${deviceCategory} in ('mobile','tablet')"))
        self.assertEqual(dims["id"][3:5], ("number", "${TABLE}.id"))
        self.assertTrue(dims["id"][7])

    def test_quotes_inside_sql_and_table_names_are_kept(self):
        rows = _ingest(
            orders="""
view: orders {
  sql_table_name: "ANALYTICS"."ORDERS" ;;
  dimension: status { type: string sql: 'open' ;; }
  dimension: raw { type: string sql: "Home" ;; }
}
view: legacy { sql_table_name: [proj:ds.t] ;; }
"""
        )
        views = _by_name(rows["LOOKML_VIEW"])
        self.assertEqual(views["orders"][1], '"ANALYTICS"."ORDERS"')
        self.assertEqual(views["legacy"][1], "[proj:ds.t]")
        dims = _by_name(rows["LOOKML_DIMENSION"], 1)
        self.assertEqual((dims["status"][4], dims["raw"][4]), ("'open'", '"Home"'))

    def test_an_apostrophe_inside_an_html_value_does_not_swallow_the_rest_of_the_file(self):
        rows = _ingest(
            orders="""
view: nav {
  dimension: navigation {
    type: string
    html: <!-- NOTE: there's a bug in the dashboard url -->
      {% if x == false %}<span>{{ _explore._dashboard_url }}</span>{% endif %} ;;
  }
  dimension: after { type: number }
}
"""
        )
        self.assertEqual(sorted(_by_name(rows["LOOKML_DIMENSION"], 1)), ["after", "navigation"])

    def test_names_may_start_with_a_digit(self):
        rows = _ingest(
            orders="view: weekly {\n  measure: 28_days_active_users { type: count }\n  dimension: 3_pointers { type: number }\n}\n"
        )
        self.assertEqual([row[1] for row in rows["LOOKML_MEASURE"]], ["28_days_active_users"])
        self.assertEqual([row[1] for row in rows["LOOKML_DIMENSION"]], ["3_pointers"])

    def test_a_table_name_that_starts_on_the_next_line_with_liquid(self):
        rows = _ingest(
            usage="""
view: storage_usage {
  sql_table_name:
    {% if database_name._in_query %}
    SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
    {% else %}
    SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
    {% endif %} ;;
}
"""
        )
        table = rows["LOOKML_VIEW"][0][1]
        self.assertIn("DATABASE_STORAGE_USAGE_HISTORY", table)
        self.assertIn("{% endif %}", table)

    def test_measure_filters_in_both_syntaxes(self):
        rows = _ingest(
            orders="""
view: orders {
  measure: old_style { type: count filters: [status: "complete", region: "EU"] }
  measure: new_style { type: count filters: { field: status value: "complete" } }
  measure: none { type: count }
}
"""
        )
        filters = {row[1]: row[6] for row in rows["LOOKML_MEASURE"]}
        self.assertEqual(filters["old_style"], 'status: "complete", region: "EU"')
        self.assertEqual(filters["new_style"], 'status: "complete"')
        self.assertIsNone(filters["none"])

    def test_repeated_top_level_keys_in_a_model_file_are_not_logged(self):
        # assertNoLogs hooks the "lkml" logger directly, so this also holds under pytest, which installs
        # its own log handlers and would hide a leak on stderr.
        with self.assertNoLogs("lkml", level="WARNING"):
            _ingest(model='connection: "a"\nconnection: "b"\ninclude: "/x/*.view"\ninclude: "/y/*.view"\nexplore: e { }\n')

    def test_silencing_lkml_does_not_outlive_the_parse(self):
        import logging

        before = logging.getLogger("lkml").level
        _ingest(model='connection: "a"\nexplore: e { }\n')
        self.assertEqual(logging.getLogger("lkml").level, before)

    def test_a_utf8_byte_order_mark_does_not_hide_the_first_block(self):
        rows = _ingest(orders="\ufeffview: orders {\n  dimension: id { type: number }\n}\n")
        self.assertEqual([row[0] for row in rows["LOOKML_VIEW"]], ["orders"])
        self.assertEqual([row[1] for row in rows["LOOKML_DIMENSION"]], ["id"])


class MalformedInputTests(unittest.TestCase):
    def _collect(self, **files):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name, text in files.items():
                (base / f"{name}.lkml").write_text(text)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rows = lookml._collect(sorted(base.glob("*.lkml")), base)
        return rows, stderr.getvalue()

    def test_blocks_without_a_name_are_skipped_with_a_warning_instead_of_crashing(self):
        rows, stderr = self._collect(
            a="view: { dimension: x { type: number } }\nexplore: { label: \"x\" }\nview: v { dimension: { type: number } measure: { type: count } }\n"
        )
        self.assertEqual(list(rows.views), ["v"])
        self.assertEqual((rows.dimensions, rows.measures, rows.explores), ({}, {}, {}))
        self.assertGreaterEqual(stderr.count("without a name"), 4)

    def test_a_refinement_whose_base_is_missing_warns(self):
        rows, stderr = self._collect(only='view: +orders { description: "R" }\nexplore: +e { label: "L" }\n')
        self.assertEqual(rows.views["orders"]["description"], "R")
        self.assertIn("view +orders refines a view that is not defined in any ingested file", stderr)
        self.assertIn("explore +e refines an explore", stderr)

    def test_a_base_that_cannot_be_parsed_is_reported_along_with_its_orphaned_refinement(self):
        rows, stderr = self._collect(
            a_base='view: orders {\n  description: "one"\n  description: "two"\n  sql_table_name: t ;;\n}\n',
            b_ref='view: +orders { description: "R" }\n',
        )
        self.assertEqual(rows.skipped, 1)
        self.assertIn("skipping a_base.lkml", stderr)
        self.assertIn("view +orders refines a view that is not defined", stderr)

    def test_the_summary_line_counts_skipped_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "good.lkml").write_text("view: v { dimension: x { type: string } }\n")
            (base / "bad.lkml").write_text("view: w {\n  dimension: y {\n")
            out = io.StringIO()
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
                lookml._ingest(_Destination(), sorted(base.glob("*.lkml")), base)
        self.assertIn("1 files skipped", out.getvalue())

    def test_warnings_become_github_annotations_when_running_in_actions(self):
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            out = io.StringIO()
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
                self._collect(only='view: +orders { description: "R" }\n')
        self.assertRegex(out.getvalue(), r"::warning title=Agents Schema LookML::.*view \+orders refines")

    def test_no_annotation_outside_actions(self):
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("GITHUB_ACTIONS", None)
            out = io.StringIO()
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
                self._collect(only='view: +orders { description: "R" }\n')
        self.assertNotIn("::warning", out.getvalue())

    def test_a_sql_that_swallowed_the_following_blocks_is_flagged(self):
        # A stray single `;` instead of `;;` makes the parser read on to the next `;;`.
        rows, stderr = self._collect(
            a='view: v {\n  dimension: a {\n    sql: ${TABLE}."A";\n  }\n  dimension: b {\n    sql: ${TABLE}.b ;;\n  }\n}\n'
        )
        self.assertIn("v.a contains what looks like another block", stderr)

    def test_an_unreadable_file_fails_the_run_instead_of_being_reported_as_a_parse_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a.lkml").write_text("view: v { }\n")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                with self.assertRaisesRegex(ValueError, "cannot read a.lkml"):
                    lookml._collect([base / "a.lkml"], base)

    def test_a_directory_named_like_a_lookml_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "dir.lkml").mkdir()
            (Path(tmp) / "good.lkml").write_text("view: v { }\n")
            self.assertEqual([p.name for p in lookml._load_lookml_files(Path(tmp))], ["good.lkml"])

    def test_a_second_full_definition_of_a_view_replaces_the_first_instead_of_half_merging(self):
        rows, _ = self._collect(
            a='view: v {\n  dimension: x { type: string sql: ${TABLE}.x ;; description: "first" }\n  dimension: only_first { type: number }\n}\n',
            b="view: v {\n  dimension: x { type: number }\n}\n",
        )
        self.assertEqual(rows.dimensions[("v", "x")], {"type": "number", "field_kind": "dimension"})
        self.assertNotIn(("v", "only_first"), rows.dimensions)


class ExploreTests(unittest.TestCase):
    def test_a_joins_properties_do_not_overwrite_the_explore(self):
        rows = _ingest(
            model="""
explore: orders {
  from: orders_base
  label: "Orders Explore"
  description: "Orders joined to customers"
  always_filter: {
    filters: [orders.status: "complete"]
  }
  join: customers {
    from: customer_table
    label: "Customers"
    sql_on: ${orders.customer_id} = ${customers.id} ;;
    relationship: many_to_one
  }
}
"""
        )
        self.assertEqual(
            rows["LOOKML_EXPLORE"],
            [("orders", "orders_base", "Orders Explore", "Orders joined to customers", None, "model.lkml")],
        )

    def test_from_defaults_to_the_explore_name(self):
        rows = _ingest(model="explore: orders {\n  join: customers { from: customer_table }\n}\n")
        self.assertEqual(rows["LOOKML_EXPLORE"][0][:2], ("orders", "orders"))


class RefinementTests(unittest.TestCase):
    BASE = """
view: orders {
  sql_table_name: analytics.orders ;;
  label: "Orders"
  description: "Base description"
  dimension: id {
    primary_key: yes
    type: number
    description: "Base id description"
  }
}
"""
    REFINEMENT = """
view: +orders {
  description: "Refined description"
  dimension: id { description: "Refined id description" }
  dimension: discount { type: number }
}
"""

    def _check(self, rows):
        self.assertEqual(
            rows["LOOKML_VIEW"],
            [("orders", "analytics.orders", "Orders", "Refined description", None, "a_base.lkml")],
        )
        dims = _by_name(rows["LOOKML_DIMENSION"], 1)
        self.assertEqual(sorted(dims), ["discount", "id"])
        self.assertEqual(dims["id"][3], "number")  # kept from the base
        self.assertEqual(dims["id"][5], "Refined id description")  # overridden
        self.assertTrue(dims["id"][7])  # primary_key kept from the base

    def test_a_refinement_extends_and_overrides_its_base(self):
        self._check(_ingest(a_base=self.BASE, b_refinements=self.REFINEMENT))

    def test_the_result_does_not_depend_on_which_file_sorts_first(self):
        self._check(_ingest(a_base=self.BASE, a_aaa_refinements=self.REFINEMENT))

    def test_a_refinement_without_a_base_still_produces_the_view_and_its_fields(self):
        rows = _ingest(only=self.REFINEMENT)
        self.assertEqual([row[0] for row in rows["LOOKML_VIEW"]], ["orders"])
        self.assertEqual(sorted(_by_name(rows["LOOKML_DIMENSION"], 1)), ["discount", "id"])

    def test_explores_can_be_refined_too(self):
        rows = _ingest(
            a='explore: orders {\n  label: "Orders"\n  description: "Base"\n}\n',
            b='explore: +orders {\n  description: "Refined"\n}\n',
        )
        self.assertEqual(rows["LOOKML_EXPLORE"], [("orders", "orders", "Orders", "Refined", None, "a.lkml")])


class RunTests(unittest.TestCase):
    def _run(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.view.lkml").write_text(text)
            dest = _Destination()
            opened = []

            def open_destination(cfg):
                opened.append(True)
                return dest

            cfg = {"warehouse": {"type": "snowflake"}, "metadata_connection": {"path": tmp}}
            with patch.object(lookml, "open_destination", open_destination), patch.object(
                lookml, "publish_builtin_skill"
            ), contextlib.redirect_stdout(open("/dev/null", "w")):
                try:
                    lookml.run(cfg)
                    error = None
                except ValueError as e:
                    error = e
        return dest, opened, error

    def test_when_no_file_can_be_parsed_the_run_fails_before_the_warehouse_is_touched(self):
        dest, opened, error = self._run("view: v {\n  dimension: x {\n")
        self.assertIsInstance(error, ValueError)
        self.assertEqual(opened, [])
        self.assertEqual(dest.calls, [])

    def test_an_unparseable_file_is_skipped_with_a_warning_and_the_rest_is_ingested(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "good.view.lkml").write_text("view: v { dimension: x { type: string } }\n")
            (Path(tmp) / "bad.view.lkml").write_text("view: w {\n  dimension: y {\n")
            stderr = io.StringIO()
            dest = _Destination()
            with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(open("/dev/null", "w")):
                lookml._ingest(dest, sorted(Path(tmp).glob("*.lkml")), Path(tmp))
        self.assertRegex(stderr.getvalue(), "skipping bad.view.lkml")
        self.assertEqual([row[0] for row in dest.rows["LOOKML_VIEW"]], ["v"])

    def test_a_valid_run_replaces_tables_then_inserts(self):
        dest, opened, error = self._run("view: v {\n  dimension: x { type: string }\n}\n")
        self.assertIsNone(error)
        kinds = [call[0] for call in dest.calls]
        self.assertLess(kinds.index("replace"), kinds.index("insert"))

    def test_no_lkml_files_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "no \\*.lkml files"):
                lookml._load_lookml_files(Path(tmp))


if __name__ == "__main__":
    unittest.main()
