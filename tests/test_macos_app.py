import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sankalp.macos import install_macos_app


class MacOSAppTests(unittest.TestCase):
    def test_installer_creates_app_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_path = Path(tmp) / "Sankalp.app"
            repo = Path(tmp) / "repo"
            repo.mkdir()

            with patch("sankalp.macos.is_macos", return_value=True):
                result = install_macos_app(app_path=app_path, repo_root=repo)

            self.assertTrue(result["ok"])
            self.assertTrue((app_path / "Contents" / "Info.plist").exists())
            plist = (app_path / "Contents" / "Info.plist").read_text(encoding="utf-8")
            self.assertIn("LSUIElement", plist)
            executable = app_path / "Contents" / "MacOS" / "Sankalp"
            self.assertTrue(executable.exists())
            if result["launcher_type"] == "shell":
                launcher = executable.read_text(encoding="utf-8")
                self.assertIn(str(repo), launcher)
                self.assertIn("-m sankalp.daemon", launcher)
            else:
                launcher_source = app_path / "Contents" / "Resources" / "launcher.m"
                source = launcher_source.read_text(encoding="utf-8")
                self.assertIn(str(repo), source)
                self.assertIn("sankalp.daemon", source)
                self.assertIn("NSStatusItem", source)
                self.assertIn("sankalp_icon", source)
                self.assertIn("Status: Live", source)
                self.assertIn("Open WebUI", source)
                self.assertIn("Base URL", source)
                self.assertIn("Copy", source)
                self.assertIn("/api/app/update", source)
                self.assertIn("Update Sankalp", source)
                self.assertIn("update_available", source)
                self.assertIn("Sankalp.menu.lock", source)


if __name__ == "__main__":
    unittest.main()
