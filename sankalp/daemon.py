from __future__ import annotations

import argparse
import signal
import time
from threading import Event

from sankalp.gateway import TelegramGateway, TelegramGatewayConfig
from sankalp.server import AGENT, start_http_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Sankalp as a long-lived local daemon.")
    parser.add_argument("--no-http", action="store_true", help="Do not start the loopback WebUI/API server.")
    parser.add_argument("--telegram", action="store_true", help="Enable the Telegram messaging gateway.")
    args = parser.parse_args(argv)

    stop_event = Event()

    def request_stop(signum: int, _frame: object) -> None:
        print(f"Sankalp daemon received signal {signum}; shutting down.", flush=True)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    if not args.no_http:
        start_http_server(block=False)

    telegram_config = TelegramGatewayConfig.from_settings()
    telegram_enabled = args.telegram or telegram_config.enabled
    if telegram_enabled:
        if not telegram_config.token:
            print("Set SANKALP_TELEGRAM_BOT_TOKEN before enabling --telegram.", flush=True)
            if args.no_http:
                return 2
            telegram_enabled = False
        else:
            TelegramGateway(AGENT, telegram_config).run_forever(stop_event=stop_event)
            return 0

    if args.no_http:
        print("No daemon surfaces enabled. Use --telegram or omit --no-http.", flush=True)
        return 2

    print("Sankalp daemon is running with the loopback WebUI/API only.", flush=True)
    while not stop_event.is_set():
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
