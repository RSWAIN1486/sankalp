import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

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


if __name__ == "__main__":
    unittest.main()
