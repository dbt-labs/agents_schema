"""A bad input file must fail the run before any warehouse table is replaced.

Connectors replace their tables and then insert rows. If parsing happened after the replace, one bad file
would leave empty tables behind (while AGENTS.ROOT still advertises them), so every connector parses first.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import dbt, omni, osi, sigma

FIXTURES_INVALID = Path(__file__).parent / "fixtures_invalid"


class _Destination:
    def __init__(self):
        self.calls = []
        self.inserted = {}

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
        self.inserted[table.name.split(".")[-1]] = list(rows)

    def delete_rows(self, *args):
        self.calls.append(("delete",))


def _run(module, path, **patches):
    """Run `module.run` against a recording destination; return (destination, times opened, error, stderr)."""
    dest = _Destination()
    opened = []

    def open_destination(cfg):
        opened.append(True)
        return dest

    cfg = {"warehouse": {"type": "snowflake"}, "metadata_connection": {"path": str(path)}}
    stderr = io.StringIO()
    error = None
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(module, "open_destination", open_destination))
        if hasattr(module, "publish_builtin_skill"):
            stack.enter_context(patch.object(module, "publish_builtin_skill"))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(stderr))
        try:
            module.run(cfg)
        except (ValueError, FileNotFoundError) as e:
            error = e
    return dest, opened, error, stderr.getvalue()


class ParseBeforeReplaceTests(unittest.TestCase):
    def test_dbt_manifest_node_without_a_name_fails_before_the_warehouse_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "target").mkdir()
            (Path(tmp) / "target" / "manifest.json").write_text(
                json.dumps({"nodes": {"model.p.m": {"resource_type": "model"}}})
            )
            dest, opened, error, _ = _run(dbt, tmp)

        self.assertRegex(str(error), "model.p.m has no name")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_invalid_osi_file_fails_before_the_warehouse_is_touched(self):
        dest, opened, error, _ = _run(osi, FIXTURES_INVALID)

        self.assertIsInstance(error, ValueError)
        self.assertEqual((opened, dest.calls), ([], []))

    def test_sigma_file_that_is_not_a_mapping_fails_before_the_warehouse_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.sigma.yaml").write_text("just a string\n")
            dest, opened, error, _ = _run(sigma, tmp)

        self.assertRegex(str(error), "expected a YAML mapping")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_sigma_file_with_a_yaml_syntax_error_names_the_file_instead_of_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.sigma.yaml").write_text("name: x\npages: [unclosed\n")
            dest, opened, error, _ = _run(sigma, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), r"broken\.sigma\.yaml: invalid YAML")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_osi_file_with_a_yaml_syntax_error_names_the_file_instead_of_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.osi.yaml").write_text("version: [unclosed\n")
            dest, opened, error, _ = _run(osi, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), r"broken\.osi\.yaml: invalid YAML")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_osi_document_of_another_spec_version_says_which_version_is_supported(self):
        # dbt emits OSI 0.1.1; the bundled schema is a different version, and "'dialects' was unexpected"
        # says nothing about that.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "dbt.osi.yaml").write_text('version: "0.1.1"\ndialects: [ANSI_SQL]\nsemantic_model: []\n')
            dest, opened, error, _ = _run(osi, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), r"unsupported OSI version '0\.1\.1'; .*reads OSI 0\.2\.0\.dev0")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_dbt_manifest_with_the_wrong_shape_is_a_clear_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "target").mkdir()
            (Path(tmp) / "target" / "manifest.json").write_text('{"nodes": null}')
            dest, opened, error, _ = _run(dbt, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), "dbt manifest: input is not in the expected shape")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_sigma_file_with_the_wrong_shape_is_a_clear_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.sigma.yaml").write_text("name: x\npages:\n")
            dest, opened, error, _ = _run(sigma, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), "sigma: input is not in the expected shape")
        self.assertEqual((opened, dest.calls), ([], []))

    def test_a_yaml_date_that_does_not_exist_names_the_file(self):
        # PyYAML resolves 2001-13-45 as a timestamp and raises a bare ValueError that names nothing.
        for module, filename in ((sigma, "a.sigma.yaml"), (osi, "a.osi.yaml")):
            with self.subTest(connector=module.__name__), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / filename).write_text("when: 2001-13-45\n")
                dest, opened, error, _ = _run(module, tmp)

                self.assertRegex(str(error), rf"{filename}: invalid YAML")
                self.assertEqual((opened, dest.calls), ([], []))

    def test_a_good_run_still_replaces_tables_before_inserting(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "target").mkdir()
            (Path(tmp) / "target" / "manifest.json").write_text(
                json.dumps({"nodes": {"model.p.m": {"resource_type": "model", "name": "m"}}})
            )
            dest, opened, error, _ = _run(dbt, tmp)

        self.assertIsNone(error)
        kinds = [call[0] for call in dest.calls]
        self.assertLess(max(i for i, k in enumerate(kinds) if k == "replace"), kinds.index("insert"))
        self.assertEqual(len(dest.inserted["DBT_MODEL"]), 1)


class OmniWarningTests(unittest.TestCase):
    def _omni_dir(self, tmp):
        base = Path(tmp)
        (base / "good.view.yaml").write_text("# Reference this view as s__good\nschema: s\ntable_name: GOOD\n")
        (base / "broken.view.yaml").write_text("schema: s\ntable_name: [unclosed\n  bad: : :\n")
        (base / "list.view.yaml").write_text("- just\n- a list\n")
        (base / "broken.topic.yaml").write_text("base_view: [oops\n")
        return base

    def test_unusable_files_are_skipped_with_a_warning_naming_each_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest, opened, error, stderr = _run(omni, self._omni_dir(tmp))

        self.assertIsNone(error)
        self.assertEqual([row[0] for row in dest.inserted["OMNI_VIEW"]], ["s__good"])
        for name in ("broken.view.yaml", "list.view.yaml", "broken.topic.yaml"):
            self.assertIn(f"skipped {name}", stderr)
        self.assertIn("expected a YAML mapping, got list", stderr)

    def test_a_directory_with_no_omni_files_is_an_error_not_an_empty_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest, opened, error, _ = _run(omni, tmp)

        self.assertIsInstance(error, FileNotFoundError)
        self.assertEqual((opened, dest.calls), ([], []))

    def test_when_every_file_is_unusable_the_run_fails_instead_of_emptying_the_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "list.view.yaml").write_text("- just\n- a list\n")
            (Path(tmp) / "broken.topic.yaml").write_text("base_view: [oops\n")
            dest, opened, error, stderr = _run(omni, tmp)

        self.assertIsInstance(error, ValueError)
        self.assertRegex(str(error), "none of the 2 Omni files")
        self.assertIn("skipped list.view.yaml", stderr)
        self.assertEqual((opened, dest.calls), ([], []))

    def test_falsy_non_mapping_yaml_is_skipped_with_a_warning_too(self):
        for text in ("[]\n", "0\n", "false\n", '""\n'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "good.view.yaml").write_text("# Reference this view as s__good\nschema: s\n")
                (Path(tmp) / "odd.view.yaml").write_text(text)
                dest, _, error, stderr = _run(omni, tmp)

                self.assertIsNone(error)
                self.assertEqual([row[0] for row in dest.inserted["OMNI_VIEW"]], ["s__good"])
                self.assertIn("skipped odd.view.yaml", stderr)

    def test_an_empty_or_comment_only_file_is_still_kept_as_an_empty_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "empty.view.yaml").write_text("# Reference this view as s__empty\n")
            dest, _, error, stderr = _run(omni, tmp)

        self.assertIsNone(error)
        self.assertEqual([row[0] for row in dest.inserted["OMNI_VIEW"]], ["s__empty"])
        self.assertEqual(stderr, "")

    def test_a_directory_named_like_a_view_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.view.yaml").mkdir()
            (Path(tmp) / "good.view.yaml").write_text("# Reference this view as s__good\nschema: s\n")
            dest, _, error, _ = _run(omni, tmp)

        self.assertIsNone(error)
        self.assertEqual([row[0] for row in dest.inserted["OMNI_VIEW"]], ["s__good"])

    def test_a_yaml_date_that_does_not_exist_is_skipped_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "good.view.yaml").write_text("# Reference this view as s__good\nschema: s\n")
            (Path(tmp) / "dated.view.yaml").write_text("when: 2001-13-45\n")
            dest, _, error, stderr = _run(omni, tmp)

        self.assertIsNone(error)
        self.assertIn("skipped dated.view.yaml", stderr)

    def test_a_clean_directory_produces_no_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "good.view.yaml").write_text("# Reference this view as s__good\nschema: s\n")
            _, _, error, stderr = _run(omni, tmp)

        self.assertIsNone(error)
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
