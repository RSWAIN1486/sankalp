#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UPDATE_JSON="$ROOT_DIR/update.json"
VERSION_FILE="$ROOT_DIR/sankalp/__init__.py"

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh [patch|minor|major|X.Y.Z] [options]

# Do release bump + manifest update
scripts/release.sh patch --title "Sidebar menu overflow fix"

# Manual notes override
scripts/release.sh patch --title "Sidebar menu overflow fix" \
  --notes "Conversation menu no longer causes sidebar scrollbar;Popover now viewport-anchored;Improved menu close behavior"
  
Options:
  --title "Release title"          Set manifest title explicitly.
  --notes "note1;note2;note3"      Set release notes explicitly (semicolon-separated).
  --notes-file path.txt            Set release notes from file (one note per line).
  --channel stable                 Manifest channel (default: existing value or stable).
  --min-supported X.Y.Z            minimum_supported_version override.
  --max-notes N                    Max auto-generated notes (default: 8).
  --dry-run                        Show planned changes without writing files.
  -h, --help                       Show help.

Notes behavior:
  If --notes / --notes-file are not passed, notes are auto-generated from git commit
  subjects since the previous release point:
  1) tag v<current-version> (if present), else
  2) last commit that touched update.json, else
  3) last 8 commits.
EOF
}

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required tool: $1" >&2
    exit 1
  fi
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf "%s" "$value"
}

current_version() {
  sed -n 's/^__version__ = "\(.*\)"/\1/p' "$VERSION_FILE"
}

bump_version() {
  local current="$1"
  local mode="$2"
  CURRENT_VERSION="$current" BUMP_MODE="$mode" python3 - <<'PY'
import os, re, sys

current = os.environ["CURRENT_VERSION"].strip()
mode = os.environ["BUMP_MODE"].strip()
match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", current)
if not match:
    print(f"Unsupported current version format: {current}", file=sys.stderr)
    sys.exit(1)

major, minor, patch = map(int, match.groups())
if mode == "patch":
    patch += 1
elif mode == "minor":
    minor += 1
    patch = 0
elif mode == "major":
    major += 1
    minor = 0
    patch = 0
else:
    explicit = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", mode)
    if not explicit:
        print(f"Unsupported bump mode/version: {mode}", file=sys.stderr)
        sys.exit(1)
    major, minor, patch = map(int, explicit.groups())

print(f"{major}.{minor}.{patch}")
PY
}

collect_notes_from_commits() {
  local max_notes="$1"
  local current="$2"

  local range=""
  if git -C "$ROOT_DIR" rev-parse -q --verify "refs/tags/v$current" >/dev/null 2>&1; then
    range="v$current..HEAD"
  else
    local last_update_commit
    last_update_commit="$(git -C "$ROOT_DIR" log -n 1 --format=%H -- update.json 2>/dev/null || true)"
    if [ -n "$last_update_commit" ]; then
      range="${last_update_commit}..HEAD"
    fi
  fi

  local log_args=(--no-merges --format=%s)
  if [ -n "$range" ]; then
    log_args+=("$range")
  else
    log_args+=("-n" "$max_notes")
  fi

  git -C "$ROOT_DIR" log "${log_args[@]}" | awk 'NF {print}'
}

write_manifest() {
  local next_version="$1"
  local channel="$2"
  local title="$3"
  local notes_json="$4"
  local min_supported="$5"
  NEXT_VERSION="$next_version" CHANNEL="$channel" TITLE="$title" NOTES_JSON="$notes_json" MIN_SUPPORTED="$min_supported" UPDATE_JSON="$UPDATE_JSON" python3 - <<'PY'
import json, os
from pathlib import Path

path = Path(os.environ["UPDATE_JSON"])
payload = {}
if path.exists():
    payload = json.loads(path.read_text(encoding="utf-8"))

payload["version"] = os.environ["NEXT_VERSION"]
payload["channel"] = os.environ["CHANNEL"] or payload.get("channel") or "stable"
payload["title"] = os.environ["TITLE"]
payload["notes"] = json.loads(os.environ["NOTES_JSON"])
if os.environ["MIN_SUPPORTED"]:
    payload["minimum_supported_version"] = os.environ["MIN_SUPPORTED"]
elif "minimum_supported_version" not in payload:
    payload["minimum_supported_version"] = "0.1.0"

path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

write_version_file() {
  local next_version="$1"
  NEXT_VERSION="$next_version" VERSION_FILE="$VERSION_FILE" python3 - <<'PY'
import os, re
from pathlib import Path

path = Path(os.environ["VERSION_FILE"])
text = path.read_text(encoding="utf-8")
updated = re.sub(
    r'^__version__ = ".*"$',
    f'__version__ = "{os.environ["NEXT_VERSION"]}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
if updated == text:
    raise SystemExit("Could not update __version__ in sankalp/__init__.py")
path.write_text(updated, encoding="utf-8")
PY
}

main() {
  require_tool git
  require_tool python3

  local bump_mode="${1:-patch}"
  if [[ "${bump_mode:-}" == "-"* ]]; then
    bump_mode="patch"
  else
    shift || true
  fi

  local title=""
  local notes_inline=""
  local notes_file=""
  local channel=""
  local min_supported=""
  local dry_run="0"
  local max_notes="8"

  while [ $# -gt 0 ]; do
    case "$1" in
      --title) title="${2:-}"; shift 2 ;;
      --notes) notes_inline="${2:-}"; shift 2 ;;
      --notes-file) notes_file="${2:-}"; shift 2 ;;
      --channel) channel="${2:-}"; shift 2 ;;
      --min-supported) min_supported="${2:-}"; shift 2 ;;
      --max-notes) max_notes="${2:-}"; shift 2 ;;
      --dry-run) dry_run="1"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
  done

  local current
  current="$(current_version)"
  if [ -z "$current" ]; then
    echo "Could not read current version from $VERSION_FILE" >&2
    exit 1
  fi
  local next
  next="$(bump_version "$current" "$bump_mode")"

  if [ -z "$channel" ]; then
    channel="$(python3 - <<'PY'
import json, pathlib
path = pathlib.Path("update.json")
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
    print(data.get("channel", "stable"))
else:
    print("stable")
PY
)"
  fi

  if [ -z "$title" ]; then
    title="Sankalp ${next}"
  fi

  local notes_json
  if [ -n "$notes_file" ]; then
    if [ ! -f "$notes_file" ]; then
      echo "Notes file not found: $notes_file" >&2
      exit 1
    fi
    notes_json="$(NOTES_FILE="$notes_file" python3 - <<'PY'
import json, os
from pathlib import Path
notes = [line.strip() for line in Path(os.environ["NOTES_FILE"]).read_text(encoding="utf-8").splitlines() if line.strip()]
print(json.dumps(notes))
PY
)"
  elif [ -n "$notes_inline" ]; then
    notes_json="$(NOTES_INLINE="$notes_inline" python3 - <<'PY'
import json, os
notes = [n.strip() for n in os.environ["NOTES_INLINE"].split(";") if n.strip()]
print(json.dumps(notes))
PY
)"
  else
    local commit_lines
    commit_lines="$(collect_notes_from_commits "$max_notes" "$current" | head -n "$max_notes")"
    notes_json="$(printf "%s\n" "$commit_lines" | python3 - <<'PY'
import json, sys
notes = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(notes))
PY
)"
    if [ "$notes_json" = "[]" ]; then
      notes_json='["Maintenance and quality improvements"]'
    fi
  fi

  echo "Current version: $current"
  echo "Next version:    $next"
  echo "Channel:         $channel"
  echo "Title:           $title"
  echo "Notes:"
  NOTES_JSON="$notes_json" python3 - <<'PY'
import json, os
for note in json.loads(os.environ["NOTES_JSON"]):
    print(f"  - {note}")
PY

  if [ "$dry_run" = "1" ]; then
    echo
    echo "Dry-run complete. No files were changed."
    exit 0
  fi

  write_manifest "$next" "$channel" "$title" "$notes_json" "$min_supported"
  write_version_file "$next"

  echo
  echo "Updated:"
  echo "  - $UPDATE_JSON"
  echo "  - $VERSION_FILE"
  echo
  echo "Next steps:"
  echo "  1) Review update.json notes"
  echo "  2) git add update.json sankalp/__init__.py"
  echo "  3) git commit -m \"release: v$next\""
  echo "  4) git tag v$next && git push origin main --tags"
}

main "$@"
