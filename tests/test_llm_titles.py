import tempfile
import unittest
from pathlib import Path

import sankalp.settings as settings_module
from sankalp.agent.llm import LLMAdapter


class TitleGenerationTests(unittest.TestCase):
    def test_title_uses_global_openai_nano_over_selected_provider(self):
        seen = {}

        class CaptureLLM(LLMAdapter):
            def _openai(self, api_key, settings, messages, memory_context, previous_response_id, attachments=None):
                seen["api_key"] = api_key
                seen["model"] = settings["openai_model"]
                seen["effort"] = settings["reasoning_effort"]
                seen["prompt"] = messages[-1]["content"]
                return {"text": "Global Nano Title"}

            def _gemini(self, settings, messages, memory_context, attachments=None):
                raise AssertionError("Gemini should not title when OpenAI nano is configured")

        old_path = settings_module.SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
                settings_module.save_settings({
                    "provider": "gemini",
                    "gemini_api_key": "gemini-test",
                    "openai_api_key": "sk-test",
                })

                title = CaptureLLM().title_for_query(
                    "can you help plan tomorrow's launch checklist",
                    {"provider": "gemini", "model": "gemini-3-pro-preview"},
                )
        finally:
            settings_module.SETTINGS_PATH = old_path

        self.assertEqual(title, "Global Nano Title")
        self.assertEqual(seen["api_key"], "sk-test")
        self.assertEqual(seen["model"], "gpt-5.4-nano")
        self.assertEqual(seen["effort"], "none")
        self.assertIn("3 to 5 words", seen["prompt"])


if __name__ == "__main__":
    unittest.main()
