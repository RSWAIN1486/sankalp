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
            executable = app_path / "Contents" / "MacOS" / "Sankalp"
            self.assertTrue(executable.exists())
            if result["launcher_type"] == "shell":
                self.assertIn(str(repo), executable.read_text(encoding="utf-8"))
            else:
                launcher_source = app_path / "Contents" / "Resources" / "launcher.c"
                self.assertIn(str(repo), launcher_source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
