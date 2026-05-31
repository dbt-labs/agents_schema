import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents_schema import cli


class CliTests(unittest.TestCase):
    def test_memory_validation_errors_return_clean_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.yml"
            path.write_text("memories: {}\n")
            stderr = io.StringIO()

            with (
                patch("agents_schema.cli.warehouse_type_from_env", return_value="snowflake"),
                contextlib.redirect_stderr(stderr),
            ):
                status = cli.main(["memory", "--memory-file", str(path)])

        self.assertEqual(status, 1)
        self.assertIn("agents-schema: error: memories must be a list", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
