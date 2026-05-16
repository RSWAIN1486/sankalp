from __future__ import annotations

import json
import os
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Protocol

from sankalp.config import GATEWAY_DIR
from sankalp.settings import load_settings


TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_CHUNK_SIZE = 3800


class TelegramClient(Protocol):
    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        ...

    def send_message(self, chat_id: int | str, text: str, thread_id: int | None = None) -> dict[str, Any]:
        ...

    def send_chat_action(self, chat_id: int | str, action: str, thread_id: int | None = None) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class TelegramGatewayConfig:
    enabled: bool = False
    token: str = ""
    allowed_user_ids: set[int] = field(default_factory=set)
    allow_all_users: bool = False
    poll_timeout: int = 30
    poll_interval: float = 1.0
    state_path: Path = GATEWAY_DIR / "telegram.json"

    @classmethod
    def from_env(cls) -> "TelegramGatewayConfig":
        token = os.environ.get("SANKALP_TELEGRAM_BOT_TOKEN", "").strip()
        timeout = _env_int("SANKALP_TELEGRAM_POLL_TIMEOUT", 30)
        interval = _env_float("SANKALP_TELEGRAM_POLL_INTERVAL", 1.0)
        return cls(
            enabled=bool(token) or os.environ.get("SANKALP_TELEGRAM_ENABLED", "").lower() in {"1", "true", "yes"},
            token=token,
            allowed_user_ids=_parse_user_ids(os.environ.get("SANKALP_TELEGRAM_ALLOWED_USERS", "")),
            allow_all_users=os.environ.get("SANKALP_TELEGRAM_ALLOW_ALL", "").lower() in {"1", "true", "yes"},
            poll_timeout=max(1, timeout),
            poll_interval=max(0.1, interval),
        )

    @classmethod
    def from_settings(cls) -> "TelegramGatewayConfig":
        settings = load_settings(include_secrets=True)
        env_config = cls.from_env()
        token = env_config.token or str(settings.get("telegram_bot_token") or "").strip()
        allowed_users = env_config.allowed_user_ids or _parse_user_ids(str(settings.get("telegram_allowed_users") or ""))
        env_enabled = os.environ.get("SANKALP_TELEGRAM_ENABLED", "").lower() in {"1", "true", "yes"}
        env_disabled = os.environ.get("SANKALP_TELEGRAM_ENABLED", "").lower() in {"0", "false", "no"}
        enabled = bool(settings.get("telegram_gateway_enabled"))
        if env_enabled or env_config.token:
            enabled = True
        if env_disabled:
            enabled = False
        return cls(
            enabled=enabled,
            token=token,
            allowed_user_ids=allowed_users,
            allow_all_users=env_config.allow_all_users or bool(settings.get("telegram_allow_all")),
            poll_timeout=env_config.poll_timeout,
            poll_interval=env_config.poll_interval,
            state_path=env_config.state_path,
        )


class TelegramBotApiClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("Telegram bot token is required.")
        self.base_url = f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "edited_message"],
        }
        if offset is not None:
            payload["offset"] = offset
        response = self._post("getUpdates", payload, timeout=timeout + 10)
        return list(response.get("result") or [])

    def send_message(self, chat_id: int | str, text: str, thread_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:TELEGRAM_MESSAGE_LIMIT],
            "disable_web_page_preview": True,
        }
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        return self._post("sendMessage", payload, timeout=30)

    def send_chat_action(self, chat_id: int | str, action: str, thread_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        return self._post("sendChatAction", payload, timeout=15)

    def _post(self, method: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=data,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API {method} failed with HTTP {exc.code}: {detail}") from exc
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {body}")
        return body


class TelegramGateway:
    def __init__(self, agent: Any, config: TelegramGatewayConfig, client: TelegramClient | None = None):
        self.agent = agent
        self.config = config
        self.client = client or TelegramBotApiClient(config.token)
        self.state = self._load_state()

    def run_forever(self, stop_event: Event | None = None) -> None:
        if not self.config.allow_all_users and not self.config.allowed_user_ids:
            print(
                "Sankalp Telegram gateway has no allowed users configured. "
                "Set SANKALP_TELEGRAM_ALLOWED_USERS or SANKALP_TELEGRAM_ALLOW_ALL=1.",
                flush=True,
            )
        print("Sankalp Telegram gateway is polling.", flush=True)
        stop_event = stop_event or Event()
        while not stop_event.is_set():
            try:
                offset = self.state.get("offset")
                updates = self.client.get_updates(offset if isinstance(offset, int) else None, self.config.poll_timeout)
                for update in updates:
                    self.handle_update(update)
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        self.state["offset"] = update_id + 1
                        self._save_state()
            except KeyboardInterrupt:
                raise
            except Exception:
                traceback.print_exc()
                time.sleep(self.config.poll_interval)

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return
        sender = message.get("from") or {}
        if sender.get("is_bot"):
            return
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return
        thread_id = message.get("message_thread_id")
        if not isinstance(thread_id, int):
            thread_id = None
        text = str(message.get("text") or "").strip()
        user_id = sender.get("id")
        if not isinstance(user_id, int):
            self._send(chat_id, "I could not identify the Telegram sender for this message.", thread_id)
            return

        if not self._is_authorized(user_id):
            self._send(
                chat_id,
                f"Sankalp Telegram access is not enabled for this user. Your Telegram user id is `{user_id}`.",
                thread_id,
            )
            return

        if not text:
            self._send(chat_id, "I can handle text messages first. File, image, and voice support will come later.", thread_id)
            return

        command_response = self._handle_command(text, chat_id, thread_id, user_id)
        if command_response is not None:
            self._send(chat_id, command_response, thread_id)
            return

        session_key = self._session_key(chat_id, thread_id)
        session_id = self._session_for_key(session_key)
        try:
            self.client.send_chat_action(chat_id, "typing", thread_id)
        except Exception:
            pass
        response = self.agent.turn(
            session_id,
            text,
            {
                "options": {
                    "source": "telegram",
                    "telegram_chat_id": str(chat_id),
                    "telegram_user_id": str(user_id),
                }
            },
        )
        next_session_id = ((response.get("session") or {}) if isinstance(response, dict) else {}).get("session_id")
        if isinstance(next_session_id, str) and next_session_id:
            self._set_session_for_key(session_key, next_session_id)
        answer = ((response.get("message") or {}) if isinstance(response, dict) else {}).get("content")
        self._send(chat_id, str(answer or "Done."), thread_id)

    def _handle_command(self, text: str, chat_id: int | str, thread_id: int | None, user_id: int) -> str | None:
        if not text.startswith("/"):
            return None
        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        session_key = self._session_key(chat_id, thread_id)
        if command in {"/start", "/help"}:
            return (
                "Sankalp is running in Telegram gateway mode.\n\n"
                "Commands:\n"
                "- /new starts a fresh Sankalp session for this chat\n"
                "- /status checks the gateway\n"
                "- /whoami shows your Telegram ids\n"
                "- /help shows this message\n\n"
                "Send any normal message to continue the current chat session."
            )
        if command == "/whoami":
            return f"Telegram user id: `{user_id}`\nTelegram chat id: `{chat_id}`"
        if command == "/status":
            session_id = self._session_for_key(session_key)
            return f"Sankalp Telegram gateway is running. Session: `{session_id}`"
        if command == "/new":
            session = self.agent.sessions.create()
            self._set_session_for_key(session_key, session.session_id)
            return f"Started a fresh Sankalp session: `{session.session_id}`"
        return None

    def _is_authorized(self, user_id: int) -> bool:
        return self.config.allow_all_users or user_id in self.config.allowed_user_ids

    def _send(self, chat_id: int | str, text: str, thread_id: int | None = None) -> None:
        for chunk in _message_chunks(text):
            self.client.send_message(chat_id, chunk, thread_id)

    def _session_key(self, chat_id: int | str, thread_id: int | None) -> str:
        thread = str(thread_id) if thread_id is not None else "main"
        return f"telegram:{chat_id}:{thread}"

    def _session_for_key(self, key: str) -> str | None:
        sessions = self.state.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            self.state["sessions"] = {}
            sessions = self.state["sessions"]
        session_id = sessions.get(key)
        return str(session_id) if session_id else None

    def _set_session_for_key(self, key: str, session_id: str) -> None:
        sessions = self.state.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            self.state["sessions"] = sessions
        sessions[key] = session_id
        self._save_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return {"offset": None, "sessions": {}}
        try:
            data = json.loads(self.config.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"offset": None, "sessions": {}}
        if not isinstance(data, dict):
            return {"offset": None, "sessions": {}}
        data.setdefault("offset", None)
        data.setdefault("sessions", {})
        return data

    def _save_state(self) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")


def _parse_user_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            continue
    return ids


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _message_chunks(text: str) -> list[str]:
    clean = text.strip() or "Done."
    chunks: list[str] = []
    remaining = clean
    while len(remaining) > SAFE_CHUNK_SIZE:
        split_at = remaining.rfind("\n", 0, SAFE_CHUNK_SIZE)
        if split_at < SAFE_CHUNK_SIZE // 2:
            split_at = SAFE_CHUNK_SIZE
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining[:TELEGRAM_MESSAGE_LIMIT])
    return chunks or ["Done."]
