import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import sankalp.settings as settings_module
from sankalp.agent.llm import LLMAdapter


class LocalOpenAITests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
