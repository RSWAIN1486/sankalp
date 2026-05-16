# Sankalp Roadmap

This roadmap borrows the useful product patterns from agent platforms such as OpenClaw and Hermes
without changing Sankalp's local-first center of gravity.

## Gateway First

- Run Sankalp as a long-lived local daemon.
- Start with Telegram because the Bot API supports simple long polling and does not require a public
webhook.
- Keep access closed by default with allowlisted Telegram user IDs.
- Persist one Sankalp session per chat/thread so phone conversations have continuity.
- Add launchd support for macOS login startup; systemd can follow for Linux.

## Messaging Growth

- Telegram attachments: images, documents, and voice notes.
- Gateway pairing flow so a new Telegram user receives a one-time code that must be approved locally.
- `/stop` and busy-input behavior: interrupt, queue, or steer messages while an agent turn is running.
- Background tasks that return the result to the same chat when complete.
- Outbound delivery API so tools, scheduled jobs, and app events can send messages back to Telegram.

## Automation

- Cron-style scheduled tasks with natural-language creation.
- Delivery targets such as `origin`, `telegram`, and later additional channels.
- Script-only watchdog jobs for local health checks without invoking an LLM.
- Audit logs for scheduled runs, delivery results, and failures.

## Agent Depth

- Channel-scoped tool policy so Telegram can be more restrictive than the local WebUI.
- Multi-agent or workspace routing only after session state and gateway safety are solid.
- Skill lifecycle improvements: install, enable/disable, version, and eventually suggest new skills
  from repeated workflows.
- MCP-style external tool adapters once Sankalp has a stable permission and audit model.
