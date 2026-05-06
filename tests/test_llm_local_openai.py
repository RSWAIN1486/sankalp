import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import sankalp.settings as settings_module
from sankalp.agent.llm import LLMAdapter


class LocalOpenAITests(unittest.TestCase):
    def test_gemini_stream_emits_deltas(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __iter__(self):
                payload = json.dumps({"candidates": [{"content": {"parts": [{"text": "hello "}]} }]}).encode("utf-8")
                payload2 = json.dumps({"candidates": [{"content": {"parts": [{"text": "gemini"}]} }]}).encode("utf-8")
                return iter([b"data: " + payload + b"\n\n", b"data: " + payload2 + b"\n\n"])

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("sankalp.agent.llm.urllib.request.urlopen", return_value=FakeResponse()):
                events = list(LLMAdapter()._gemini_stream({"gemini_model": "gemini-2.5-flash"}, [{"role": "user", "content": "hi"}], ""))
        deltas = [event["text"] for event in events if event.get("type") == "delta"]
        self.assertEqual("".join(deltas), "hellogemini")
        self.assertEqual(events[-1]["type"], "response_id")

    def test_local_openai_chat_completions_adapter(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                seen["path"] = self.path
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps({"id": "chat_test", "choices": [{"message": {"content": "hello local"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = LLMAdapter()._local_openai(
                {
                    "local_openai_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "local_openai_model": "test-model",
                },
                [{"role": "user", "content": "hi"}],
                "memory",
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result["text"], "hello local")
        self.assertEqual(seen["path"], "/v1/chat/completions")
        self.assertEqual(seen["body"]["model"], "test-model")
        self.assertEqual(seen["body"]["messages"][0]["role"], "system")
        self.assertNotIn("temperature", seen["body"])

    def test_local_openai_grounded_memory_answers_are_deterministic(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps({"id": "grounded_test", "choices": [{"message": {"content": "grounded"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_path = settings_module.SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
                settings_module.save_settings({
                    "provider": "local_openai",
                    "local_openai_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "local_openai_model": "grounded-model",
                })
                result = LLMAdapter().complete(
                    [{"role": "user", "content": "answer"}],
                    "memory",
                    None,
                    {"provider": "local_openai", "response_mode": "grounded_memory_answer"},
                    [],
                )
        finally:
            settings_module.SETTINGS_PATH = old_path
            server.shutdown()
            server.server_close()

        self.assertEqual(result["text"], "grounded")
        self.assertEqual(seen["body"]["temperature"], 0)

    def test_provider_hello_uses_current_local_openai_settings(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps({"id": "hello_test", "choices": [{"message": {"content": "hello"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_path = settings_module.SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
                result = LLMAdapter().test_provider({
                    "provider": "local_openai",
                    "local_openai_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "local_openai_model": "hello-model",
                })
        finally:
            settings_module.SETTINGS_PATH = old_path
            server.shutdown()
            server.server_close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["model"], "hello-model")
        self.assertEqual(seen["body"]["messages"][-1]["content"], "Reply with exactly: hello")

    def test_title_for_query_uses_local_openai_provider(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps({"id": "title_test", "choices": [{"message": {"content": "Election Results"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_path = settings_module.SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
                settings_module.save_settings({
                    "provider": "local_openai",
                    "local_openai_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "local_openai_model": "title-model",
                })
                with patch.dict(os.environ, {"OPENAI_API_KEY": "", "GEMINI_API_KEY": ""}):
                    title = LLMAdapter().title_for_query("can you check for the latest election results today")
        finally:
            settings_module.SETTINGS_PATH = old_path
            server.shutdown()
            server.server_close()

        self.assertEqual(title, "Election Results")
        self.assertEqual(seen["body"]["model"], "title-model")
        self.assertIn("3 to 5 words", seen["body"]["messages"][-1]["content"])

    def test_local_openai_sends_image_attachment_as_content_part(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps({"id": "vision_test", "choices": [{"message": {"content": "saw it"}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = LLMAdapter()._local_openai(
                {
                    "local_openai_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "local_openai_model": "vision-model",
                },
                [{"role": "user", "content": "describe"}],
                "",
                [{"name": "image.png", "kind": "image", "type": "image/png", "data": "aW1hZ2U="}],
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result["text"], "saw it")
        content = seen["body"]["messages"][-1]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
