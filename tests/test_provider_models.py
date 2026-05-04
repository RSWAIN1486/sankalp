import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sankalp.provider_models as provider_models
from sankalp.provider_models import codex_status, provider_models as get_provider_models


class ProviderModelsTests(unittest.TestCase):
    def test_fallback_lists_are_available_without_keys(self):
        with patch("sankalp.provider_models.load_settings", return_value={}):
            openai = get_provider_models("openai")
            gemini = get_provider_models("gemini")

        self.assertEqual(openai["source"], "fallback")
        self.assertTrue(any(model["id"].startswith("gpt-") for model in openai["models"]))
        self.assertEqual(gemini["source"], "fallback")
        self.assertTrue(any(model["id"].startswith("gemini-") for model in gemini["models"]))

    def test_codex_status_reads_auth_json(self):
        with unittest.mock.patch("pathlib.Path.home") as home:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".codex").mkdir()
                (root / ".codex" / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x"}}), encoding="utf-8")
                home.return_value = root

                status = codex_status()

        self.assertTrue(status["logged_in"])

    def test_codex_models_fallback_when_logged_out(self):
        with patch("sankalp.provider_models.codex_status", return_value={"logged_in": False}):
            result = get_provider_models("codex")

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["error"], "not logged in")

    def test_gemini_filter_excludes_non_chat_models(self):
        self.assertTrue(provider_models._is_gemini_chat_model("gemini-3.1-pro-preview"))
        self.assertFalse(provider_models._is_gemini_chat_model("gemini-3-pro-preview"))
        self.assertFalse(provider_models._is_gemini_chat_model("gemini-3-pro-image-preview"))
        self.assertFalse(provider_models._is_gemini_chat_model("gemini-2.5-flash-preview-tts"))
        self.assertFalse(provider_models._is_gemini_chat_model("gemini-2.5-computer-use-preview-10-2025"))

    def test_openai_labels_keep_gpt_acronym(self):
        self.assertEqual(provider_models._label("gpt-5.3-codex"), "GPT-5.3 Codex")


if __name__ == "__main__":
    unittest.main()
