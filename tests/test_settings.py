import tempfile
import unittest
from pathlib import Path

import sankalp.settings as settings_module
from sankalp.settings import load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_saves_provider_and_masks_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = settings_module.SETTINGS_PATH
            settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                saved = save_settings({
                    "provider": "local_openai",
                    "local_openai_api_key": "secret",
                    "local_openai_base_url": "http://localhost:2276/v1",
                    "local_openai_model": "qwen",
                })
                public = load_settings()
                private = load_settings(include_secrets=True)
            finally:
                settings_module.SETTINGS_PATH = old_path

            self.assertEqual(saved["provider"], "local_openai")
            self.assertTrue(public["has_local_openai_api_key"])
            self.assertNotIn("local_openai_api_key", public)
            self.assertEqual(private["local_openai_api_key"], "secret")


if __name__ == "__main__":
    unittest.main()
