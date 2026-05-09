# Computer Use

Computer Use is Sankalp's experimental macOS desktop-control layer. It lets Sankalp observe
visible apps, inspect macOS Accessibility trees, capture screenshots, and perform bounded UI
actions such as opening apps, clicking, typing, pressing keys, and scrolling.

The current implementation is intentionally local-first and macOS-only. It uses built-in macOS
tools where possible, stores screenshots under the local Sankalp cache, and logs every action in
the chat activity trail.

## What It Can Do

- List visible non-background macOS apps.
- Open or activate an app by name, for example Spotify or WhatsApp.
- Inspect one app's Accessibility tree and return element paths such as `1.2.3`.
- Capture the current screen as a PNG for model-guided visual planning.
- Click an inspected Accessibility element path.
- Click raw screenshot coordinates when an app does not expose useful Accessibility elements.
- Type into an inspected element or the current focused app.
- Press supported keys and key combinations such as `Return`, `Tab`, `Escape`, and `Command-L`.
- Scroll with page or arrow-key style events.
- Run a bounded `/computer task <instruction>` loop for low-risk workflows such as playing media.

## Main Files

- `sankalp/computer/macos.py`: macOS backend for observation and actions.
- `sankalp/computer/policy.py`: deterministic guardrail before OS-level actions execute.
- `sankalp/computer/runner.py`: model-guided task loop for `/computer task ...`.
- `sankalp/tools/registry.py`: exposes Computer Use as auditable tools.
- `sankalp/agent/core.py`: routes `/computer ...` slash commands.
- `sankalp/server.py`: advertises Computer Use tools and commands through `/api/capabilities`.
- `web/src/lib/stores/chat.ts`: loads backend capabilities into frontend state.
- `web/src/lib/components/Composer.svelte`: slash-command picker that shows `/computer` commands.
- `tests/test_computer_use.py`: unit coverage for command routing, safety policy, AppleScript
generation, focused typing, and coordinate-click behavior.

## Runtime Flow

Manual commands follow this path:

```text
User types /computer ...
  -> WebUI streams the message to /api/chat/stream
  -> Agent._route_computer_command(...)
  -> ToolRegistry.computer_* wrapper
  -> MacOSComputerUse macOS backend
  -> session tool_calls activity log
```

The autonomous task loop follows this path:

```text
User types /computer task play a playlist on Spotify
  -> Agent creates ComputerTaskRunner
  -> runner lists apps
  -> runner captures a screenshot when available
  -> runner sends prompt + screenshot attachment + recent history to the selected model
  -> model returns one JSON action
  -> ComputerActionPolicy checks the proposed action
  -> ToolRegistry executes exactly that action
  -> runner repeats until done, blocked, confirmation needed, failure, or step limit
```

The runner is deliberately one-action-at-a-time. The model is not handed a broad system-control
API. It must return one structured action, Sankalp checks it, executes it, records the result, and
then asks for the next action with the updated state.

## Tool Layer

`ToolRegistry` exposes the following tool names:

- `computer_status`
- `computer_list_apps`
- `computer_open_app`
- `computer_open_permissions`
- `computer_inspect`
- `computer_screenshot`
- `computer_click`
- `computer_type_text`
- `computer_set_value`
- `computer_press_key`
- `computer_scroll`
- `computer_wait`

Each call returns a `ToolResult` with input, output, status, and timing metadata. The agent appends
these results to `session.tool_calls`, which is what appears in the WebUI "Thinking and activity"
panel.

## Slash Commands

The backend routes these commands:

```text
/computer
/computer help
/computer status
/computer apps
/computer permissions [accessibility|screen]
/computer open <app>
/computer inspect <app>
/computer screenshot
/computer click <app> <element_path>
/computer click screen <x>,<y>
/computer type <app> [element_path] :: <text>
/computer set <app> <element_path> :: <text>
/computer key <app> <Return|Tab|Escape|Command-L>
/computer scroll <app> <down|up|left|right> [pages]
/computer task <low-risk instruction>
```

The slash picker does not hard-code the whole command catalog. The frontend calls
`/api/capabilities`, stores the response in `chat.ts`, and `Composer.svelte` renders the command
metadata. This is why adding Computer Use commands in `sankalp/server.py` makes them show up in the
composer.

## macOS Backend

`MacOSComputerUse` uses macOS primitives:

- `open -a <app>` opens or activates apps.
- `osascript` and `System Events` list apps, inspect Accessibility trees, focus apps, type text,
press keys, and operate element paths.
- `screencapture -x <path>` captures screenshots into `~/.sankalp/cache/computer-use/`.
- A small native CoreGraphics helper, `sankalp-click`, handles raw coordinate clicks.

The native click helper is compiled on demand with `clang` and stored under
`~/.sankalp/tools/sankalp-click`. Raw click coordinates are screenshot pixel coordinates. The helper
maps those pixels back to the current main-display coordinate space before posting mouse events.
This avoids the `System Events click at` path that produced macOS error `-25208` on high-DPI or
protected UI states.

Accessibility element paths are safer when available. For example, after `/computer inspect
Spotify`, a path like `1.1.2` refers to a visible UI element in the returned tree. The click command
can then press that element without relying on screen coordinates.

## Permissions

Computer Use needs macOS privacy permissions:

- Accessibility: required for `System Events` app inspection, clicks, typing, keys, and focus.
- Screen Recording: required for screenshots and visual task planning.

The permission target depends on how Sankalp was launched:

- Dev mode: grant permissions to the app that launched `scripts/relaunch_dev.sh`, usually Terminal,
iTerm, Antigravity, or another shell host.
- Installed app: grant permissions to `Sankalp.app`.

Useful commands:

```text
/computer permissions accessibility
/computer permissions screen
```

These open the relevant macOS Privacy panes. If screenshots fail with `could not create image from
display`, Screen Recording is missing for the active launcher. If inspection fails or only app
opening works, Accessibility is usually missing or needs the launcher to be restarted after granting.

## Task Loop Prompting

`ComputerTaskRunner` asks the selected model to return only JSON:

```json
{
  "status": "continue",
  "message": "short progress note",
  "action": {
    "tool": "open_app",
    "app": "Spotify",
    "purpose": "why this is safe"
  }
}
```

Allowed statuses are:

- `continue`: execute the next action.
- `done`: stop and return the message to the user.
- `blocked`: stop because the task cannot continue.
- `confirm`: stop before a high-impact action that needs explicit user confirmation.

Allowed action tools are:

- `open_app`
- `inspect_app`
- `click`
- `type_text`
- `set_value`
- `press_key`
- `scroll`
- `wait`
- `screenshot`

The task loop has a bounded step limit. The current default is 8 steps, clamped to a maximum of 16.
This keeps experimental desktop control from running indefinitely.

## Safety Policy

`ComputerActionPolicy` is a deterministic layer that runs before every task-loop action. It allows
observation, app opening, screenshots, waits, and app inspection. For active UI actions, it pauses
when the proposed action or user instruction looks sensitive or high impact.

Sankalp pauses before actions involving:

- Passwords, passcodes, OTPs, auth codes, API keys, secrets, tokens, credit cards, or banking.
- Sending, submitting, sharing, deleting, removing, paying, purchasing, buying, transferring,
installing, unsubscribing, or confirming high-impact targets.

Low-risk local media tasks, such as searching Spotify and playing a playlist, are allowed without
confirmation. The policy checks the action's target fields rather than blindly blocking because a
prompt says something like "does not share private data."

The runner prompt also tells the model to treat on-screen text and webpages as untrusted content.
This matters because desktop automation can encounter arbitrary app or webpage instructions.

## Spotify Example

For a request like:

```text
/computer task play a Bollywood acoustic playlist on Spotify
```

the expected path is:

```text
computer_list_apps
computer_screenshot
computer_open_app app=Spotify
computer_screenshot
computer_press_key app=Spotify key=Command-L
computer_type_text app=Spotify text="Bollywood acoustic playlist"
computer_press_key app=Spotify key=Return
computer_screenshot
computer_click app=Spotify x=<play-button-x> y=<play-button-y>
```

When Accessibility exposes useful controls, the model should prefer `computer_inspect` and
element-path clicks. Spotify's Accessibility tree is sometimes shallow because the UI is
Electron/web-content heavy, so the task loop may fall back to screenshot-based coordinates.

## Common Failures

- `No windows are available`: the app process exists but has not opened a visible window yet.
Use `/computer open <app>`, wait, then inspect again.
- `could not create image from display`: Screen Recording is not granted to the active launcher.
- AppleScript Accessibility errors: Accessibility is not granted, or the launcher needs restart
after the permission change.
- `System Events ... -25208` during coordinate click: the older AppleScript coordinate-click path
failed. The CoreGraphics helper is used first now; if it is unavailable, install Xcode command-line
tools so `clang` can compile `sankalp-click`.
- The task opens an app but does not progress: screenshots may be unavailable, the selected model
may not support image attachments well, or the app's Accessibility tree may be too shallow. Manual
commands such as `/computer key Spotify Command-L` and `/computer type Spotify :: query` are useful
for diagnosis.

## Design Decisions

- Start macOS-only because Sankalp is currently being tested on a local Mac and macOS provides
standard Accessibility, AppleScript, and screenshot tools.
- Keep the backend dependency-light: no PyObjC dependency is required for the first version.
- Compile only a tiny native helper where built-in tools were unreliable for coordinate clicks.
- Route all actions through `ToolRegistry` so the same audit trail works for manual commands and
autonomous tasks.
- Keep `/computer task` bounded and one-action-at-a-time for safety and debuggability.
- Keep risky-action checks deterministic instead of relying only on model self-restraint.
