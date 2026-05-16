import os
import tempfile
import unittest
from pathlib import Path

import sankalp.settings as settings_module
from sankalp import config as config_module
from sankalp.settings import allowed_roots_from_settings, load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_agent_home_directories_are_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_values = {
                "STATE_DIR": config_module.STATE_DIR,
                "SESSION_DIR": config_module.SESSION_DIR,
                "SKILLS_DIR": config_module.SKILLS_DIR,
                "HOOKS_DIR": config_module.HOOKS_DIR,
                "GATEWAY_DIR": config_module.GATEWAY_DIR,
                "LOGS_DIR": config_module.LOGS_DIR,
                "CACHE_DIR": config_module.CACHE_DIR,
                "SANDBOXES_DIR": config_module.SANDBOXES_DIR,
                "MEMORIES_DIR": config_module.MEMORIES_DIR,
                "WEBUI_DIR": config_module.WEBUI_DIR,
                "TOOLS_DIR": config_module.TOOLS_DIR,
                "VAULT_DIR": config_module.VAULT_DIR,
                "SOUL_FILE": config_module.SOUL_FILE,
            }
            root = Path(tmp) / ".sankalp"
            try:
                config_module.STATE_DIR = root
                config_module.SESSION_DIR = root / "sessions"
                config_module.SKILLS_DIR = root / "skills"
                config_module.HOOKS_DIR = root / "hooks"
                config_module.GATEWAY_DIR = root / "gateway"
                config_module.LOGS_DIR = root / "logs"
                config_module.CACHE_DIR = root / "cache"
                config_module.SANDBOXES_DIR = root / "sandboxes"
                config_module.MEMORIES_DIR = root / "memories"
                config_module.WEBUI_DIR = root / "webui"
                config_module.TOOLS_DIR = root / "tools"
                config_module.VAULT_DIR = root / "obsidian-vault"
                config_module.SOUL_FILE = root / "SOUL.md"

                config_module.ensure_dirs()
            finally:
                for key, value in old_values.items():
                    setattr(config_module, key, value)

            for name in ["sessions", "skills", "hooks", "gateway", "logs", "cache", "sandboxes", "memories", "webui", "tools", "obsidian-vault"]:
                self.assertTrue((root / name).is_dir(), name)
            self.assertTrue((root / "SOUL.md").is_file())

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

    def test_saves_research_settings_and_masks_firecrawl_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = settings_module.SETTINGS_PATH
            settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                save_settings({
                    "firecrawl_base_url": "http://localhost:3002",
                    "firecrawl_api_key": "fc-secret",
                    "searxng_base_url": "http://localhost:8080",
                })
                public = load_settings()
                private = load_settings(include_secrets=True)
            finally:
                settings_module.SETTINGS_PATH = old_path

            self.assertEqual(public["firecrawl_base_url"], "http://localhost:3002")
            self.assertEqual(public["searxng_base_url"], "http://localhost:8080")
            self.assertTrue(public["has_firecrawl_api_key"])
            self.assertNotIn("firecrawl_api_key", public)
            self.assertEqual(private["firecrawl_api_key"], "fc-secret")

    def test_saves_telegram_gateway_settings_and_masks_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = settings_module.SETTINGS_PATH
            settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                save_settings({
                    "telegram_gateway_enabled": True,
                    "telegram_bot_token": "telegram-secret",
                    "telegram_allowed_users": "123,456",
                    "telegram_allow_all": False,
                })
                public = load_settings()
                private = load_settings(include_secrets=True)
            finally:
                settings_module.SETTINGS_PATH = old_path

            self.assertTrue(public["telegram_gateway_enabled"])
            self.assertTrue(public["has_telegram_bot_token"])
            self.assertNotIn("telegram_bot_token", public)
            self.assertEqual(public["telegram_allowed_users"], "123,456")
            self.assertEqual(private["telegram_bot_token"], "telegram-secret")

    def test_allowed_roots_can_be_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = settings_module.SETTINGS_PATH
            old_env = os.environ.get("SANKALP_ALLOWED_ROOTS")
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            root_a.mkdir()
            root_b.mkdir()
            settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                save_settings({"allowed_roots": f"{root_a}\n{root_b}"})
                roots = allowed_roots_from_settings()
            finally:
                settings_module.SETTINGS_PATH = old_path
                if old_env is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old_env

            self.assertEqual(roots, [root_a.resolve(), root_b.resolve()])


if __name__ == "__main__":
    unittest.main()
