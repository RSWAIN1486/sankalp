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

    def test_update_status_uses_installed_code_version_not_local_manifest(self):
        with patch("sankalp.updater._local_manifest", return_value={"version": "9.9.9"}), patch(
            "sankalp.updater.fetch_update_manifest",
            return_value={"version": "0.1.5", "title": "Release"},
        ):
            status = app_update_status()
        self.assertEqual(status["current_version"], "0.1.5")
        self.assertEqual(status["installed_manifest_version"], "9.9.9")
        self.assertFalse(status["update_available"])

    def test_update_status_handles_manifest_failure(self):
        with patch("sankalp.updater.fetch_update_manifest", side_effect=RuntimeError("offline")):
            status = app_update_status()

        self.assertFalse(status["ok"])
        self.assertIn("offline", status["error"])

    def test_start_update_requires_installer_script(self):
        with patch("sankalp.updater.ROOT", Path("/private/tmp/sankalp-missing-root")):
            result = start_app_update()

        self.assertFalse(result["ok"])

    def test_start_update_rejects_unsupported_platform(self):
        with patch("sankalp.updater.platform.system", return_value="Linux"):
            result = start_app_update()
        self.assertFalse(result["ok"])
        self.assertIn("not yet supported", result["error"])

    def test_start_update_uses_windows_installer(self):
        fake_root = Path("/private/tmp/sankalp-update-test")
        with patch("sankalp.updater.platform.system", return_value="Windows"), patch("sankalp.updater.ROOT", fake_root):
            result = start_app_update()
        self.assertFalse(result["ok"])
        self.assertIn("install_windows.ps1", result["error"])


if __name__ == "__main__":
    unittest.main()
