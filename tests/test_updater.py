import unittest
from pathlib import Path
from unittest.mock import patch

from sankalp.updater import _is_newer_version, app_update_status, start_app_update


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(_is_newer_version("0.1.2", "0.1.1"))
        self.assertTrue(_is_newer_version("0.2.0", "0.1.9"))
        self.assertFalse(_is_newer_version("0.1.1", "0.1.1"))
        self.assertFalse(_is_newer_version("0.1.0", "0.1.1"))

    def test_update_status_marks_newer_manifest_available(self):
        with patch("sankalp.updater.fetch_update_manifest", return_value={"version": "9.0.0", "title": "Test update"}):
            status = app_update_status()

        self.assertTrue(status["ok"])
        self.assertTrue(status["update_available"])
        self.assertEqual(status["latest_version"], "9.0.0")

    def test_update_status_handles_manifest_failure(self):
        with patch("sankalp.updater.fetch_update_manifest", side_effect=RuntimeError("offline")):
            status = app_update_status()

        self.assertFalse(status["ok"])
        self.assertIn("offline", status["error"])

    def test_start_update_requires_installer_script(self):
        with patch("sankalp.updater.ROOT", Path("/private/tmp/sankalp-missing-root")):
            result = start_app_update()

        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
