import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sankalp.settings as settings_module
from sankalp.gateway.telegram import TelegramGateway, TelegramGatewayConfig, _message_chunks
from sankalp.settings import save_settings


class FakeSessionStore:
    def __init__(self):
        self.count = 0

    def create(self):
        self.count += 1
        return type("Session", (), {"session_id": f"session_{self.count}"})()


class FakeAgent:
    def __init__(self):
        self.sessions = FakeSessionStore()
        self.turns = []

    def turn(self, session_id, content, request=None):
        next_session = session_id or "session_from_turn"
        self.turns.append({"session_id": session_id, "content": content, "request": request or {}})
        return {
            "session": {"session_id": next_session},
            "message": {"content": f"reply to {content}"},
        }


class FakeTelegramClient:
    def __init__(self):
        self.sent = []
        self.actions = []

    def get_updates(self, offset, timeout):
        return []

    def send_message(self, chat_id, text, thread_id=None):
        self.sent.append({"chat_id": chat_id, "text": text, "thread_id": thread_id})
        return {"ok": True}

    def send_chat_action(self, chat_id, action, thread_id=None):
        self.actions.append({"chat_id": chat_id, "action": action, "thread_id": thread_id})
        return {"ok": True}


def message_update(text, user_id=100, chat_id=200, update_id=1):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False, "first_name": "R"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


class TelegramGatewayTests(unittest.TestCase):
    def test_denies_unknown_user_and_does_not_call_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent()
            client = FakeTelegramClient()
            config = TelegramGatewayConfig(
                token="test",
                allowed_user_ids={101},
                state_path=Path(tmp) / "telegram.json",
            )
            gateway = TelegramGateway(agent, config, client)

            gateway.handle_update(message_update("hello", user_id=100))

            self.assertEqual(agent.turns, [])
            self.assertIn("not enabled", client.sent[0]["text"])
            self.assertIn("100", client.sent[0]["text"])

    def test_authorized_text_routes_to_agent_and_persists_session_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "telegram.json"
            agent = FakeAgent()
            client = FakeTelegramClient()
            config = TelegramGatewayConfig(
                token="test",
                allowed_user_ids={100},
                state_path=state_path,
            )
            gateway = TelegramGateway(agent, config, client)

            gateway.handle_update(message_update("hello"))
            gateway.handle_update(message_update("again", update_id=2))

            self.assertEqual(agent.turns[0]["session_id"], None)
            self.assertEqual(agent.turns[1]["session_id"], "session_from_turn")
            self.assertEqual(agent.turns[0]["request"]["options"]["source"], "telegram")
            self.assertEqual(client.sent[-1]["text"], "reply to again")
            self.assertIn("session_from_turn", state_path.read_text(encoding="utf-8"))

    def test_new_command_resets_chat_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent()
            client = FakeTelegramClient()
            config = TelegramGatewayConfig(
                token="test",
                allowed_user_ids={100},
                state_path=Path(tmp) / "telegram.json",
            )
            gateway = TelegramGateway(agent, config, client)

            gateway.handle_update(message_update("/new"))

            self.assertEqual(agent.turns, [])
            self.assertIn("Started a fresh", client.sent[0]["text"])
            self.assertIn("session_1", client.sent[0]["text"])

    def test_message_chunks_keep_large_responses_under_telegram_limit(self):
        chunks = _message_chunks("x" * 9000)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))

    def test_config_loads_from_sankalp_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = settings_module.SETTINGS_PATH
            settings_module.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                save_settings({
                    "telegram_gateway_enabled": True,
                    "telegram_bot_token": "token-from-settings",
                    "telegram_allowed_users": "100,200",
                })
                with patch.dict("os.environ", {}, clear=True):
                    config = TelegramGatewayConfig.from_settings()
            finally:
                settings_module.SETTINGS_PATH = old_path

            self.assertTrue(config.enabled)
            self.assertEqual(config.token, "token-from-settings")
            self.assertEqual(config.allowed_user_ids, {100, 200})


if __name__ == "__main__":
    unittest.main()
