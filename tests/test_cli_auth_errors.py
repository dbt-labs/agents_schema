import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.auth.exceptions import RefreshError

from agents_schema import cli


def _run_cli(argv):
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stderr.getvalue()


class GoogleAuthFailureTests(unittest.TestCase):
    def test_google_auth_failure_is_a_clean_error_not_a_traceback(self):
        with patch("agents_schema.cli.dbt.run", side_effect=RefreshError("sts exchange rejected")):
            with patch("agents_schema.cli.warehouse_type_from_env", return_value="bigquery"):
                code, stderr = _run_cli(["dbt", "--project-dir", "."])

        self.assertEqual(code, 1)
        self.assertIn("agents-schema: error: Google authentication failed: sts exchange rejected", stderr)
        self.assertIn("id-token: write", stderr)
        # The hint must not assume Workload Identity Federation: a revoked service-account key raises the same error.
        self.assertIn("if you use Workload Identity Federation", stderr)
        self.assertIn("otherwise check that the service account key", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_real_google_auth_refresh_failure_is_reported_cleanly(self):
        # Mirrors the credentials file google-github-actions/auth writes for Workload
        # Identity Federation. The subject-token file is missing, so google-auth fails
        # locally (no network) with a real RefreshError while resolving credentials.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "lkml").mkdir()
            (tmp_path / "lkml" / "a.view.lkml").write_text('view: v {\n  label: "V"\n}\n')
            credentials_file = tmp_path / "credentials.json"
            credentials_file.write_text(
                json.dumps(
                    {
                        "type": "external_account",
                        "audience": "//iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/providers/g",
                        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                        "token_url": "https://sts.googleapis.com/v1/token",
                        "credential_source": {"file": str(tmp_path / "missing-oidc-token")},
                    }
                )
            )
            env = {
                "GOOGLE_APPLICATION_CREDENTIALS": str(credentials_file),
                "WAREHOUSE_CREDENTIALS": json.dumps(
                    {"type": "bigquery", "project_id": "my-proj", "auth_method": "adc"}
                ),
            }
            with patch.dict("os.environ", env, clear=True):
                code, stderr = _run_cli(["looker", "--lookml-dir", str(tmp_path / "lkml")])

        self.assertEqual(code, 1)
        self.assertIn("Google authentication failed", stderr)
        self.assertIn("missing-oidc-token", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_application_default_credentials_is_still_a_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "lkml").mkdir()
            (tmp_path / "lkml" / "a.view.lkml").write_text('view: v {\n  label: "V"\n}\n')
            env = {
                "HOME": str(tmp_path / "home"),
                "CLOUDSDK_CONFIG": str(tmp_path / "gcloud"),
                # Documented google-auth switch: skip probing the GCE metadata server so the
                # test never touches the network.
                "NO_GCE_CHECK": "true",
                "WAREHOUSE_CREDENTIALS": json.dumps(
                    {"type": "bigquery", "project_id": "my-proj", "auth_method": "adc"}
                ),
            }
            with patch.dict("os.environ", env, clear=True):
                code, stderr = _run_cli(["looker", "--lookml-dir", str(tmp_path / "lkml")])

        self.assertEqual(code, 1)
        self.assertIn("no Application Default Credentials were found", stderr)
        self.assertNotIn("Google authentication failed", stderr)


if __name__ == "__main__":
    unittest.main()
