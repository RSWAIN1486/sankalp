import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sankalp.agent import Agent
from sankalp.computer import ComputerActionPolicy, ComputerTaskRunner, MacOSComputerUse
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.tools import ToolRegistry
from sankalp.tools.base import ToolResult


class ComputerUseTests(unittest.TestCase):
    def test_status_reports_non_macos_unavailable(self):
        with patch("platform.system", return_value="Linux"):
            status = MacOSComputerUse().status()

        self.assertFalse(status["is_macos"])
        self.assertFalse(status["available"])

    def test_list_apps_parses_system_events_output(self):
        completed = Mock(returncode=0, stdout="Spotify, Terminal, Finder\n", stderr="")
        with patch("platform.system", return_value="Darwin"), patch("subprocess.run", return_value=completed):
            output = MacOSComputerUse().list_apps()

        self.assertEqual(output["apps"], ["Finder", "Spotify", "Terminal"])
        self.assertEqual(output["count"], 3)

    def test_invalid_element_path_is_rejected_before_osascript(self):
        with patch("platform.system", return_value="Darwin"), patch("subprocess.run") as run:
            output = MacOSComputerUse().click(app="Spotify", element_path="../../bad")

        self.assertFalse(output["ok"])
        run.assert_not_called()

    def test_type_text_can_target_current_focus(self):
        completed = Mock(returncode=0, stdout="", stderr="")
        with patch("platform.system", return_value="Darwin"), patch("subprocess.run", return_value=completed) as run:
            output = MacOSComputerUse().type_text(app="Spotify", element_path="", text="Bollywood Acoustic")

        self.assertTrue(output["ok"])
        script = run.call_args.args[0][-1]
        self.assertIn('tell process "Spotify" to set frontmost to true', script)
        self.assertIn('keystroke "Bollywood Acoustic"', script)

    def test_coordinate_click_prefers_native_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "sankalp-click"
            helper.write_text("#!/bin/sh\n", encoding="utf-8")
            completed = Mock(
                returncode=0,
                stdout="input_x=1994 input_y=425 click_x=997.00 click_y=212.50 pixels_w=3024 pixels_h=1964 bounds_w=1512.00 bounds_h=982.00",
                stderr="",
            )
            computer = MacOSComputerUse()
            with patch("platform.system", return_value="Darwin"), patch.object(computer, "_click_helper", return_value=helper), patch("subprocess.run", return_value=completed):
                output = computer.click(x=1994, y=425)

        self.assertTrue(output["ok"])
        self.assertEqual(output["backend"], "coregraphics-helper")
        self.assertEqual(output["click_x"], 997)
        self.assertEqual(output["pixels_w"], 3024)

    def test_inspect_script_uses_valid_applescript_helpers(self):
        script = MacOSComputerUse()._inspect_script("Spotify", 3, 45)

        self.assertIn('using terms from application "System Events"', script)
        self.assertIn("on replaceText(findText, replacementText, sourceText)", script)
        self.assertIn("& (quoted form of elementName)", script)
        self.assertIn("& (quoted form of windowTitle)", script)
        self.assertNotIn("on replaceText(findText, replaceText, sourceText)", script)

    def test_tool_registry_exposes_computer_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolRegistry(ObsidianMemory(Path(tmp)))
            with patch.object(tools.computer, "status", return_value={"available": True}):
                result = tools.call("computer_status")

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.output["available"])

    def test_policy_allows_media_playback_purpose_with_negated_risky_words(self):
        decision = ComputerActionPolicy().decide(
            {
                "tool": "click",
                "app": "Spotify",
                "element_path": "1.2.3",
                "purpose": "This is safe because it only moves focus to Spotify search and does not start playback or share private data.",
            },
            "play a Bollywood acoustic playlist on Spotify",
        )

        self.assertTrue(decision.allowed)

    def test_policy_pauses_risky_click_target(self):
        decision = ComputerActionPolicy().decide(
            {"tool": "click", "target": "Submit payment"},
            "finish checkout",
        )

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)

    def test_computer_command_routes_app_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp) / "vault")
            sessions = SessionStore(Path(tmp) / "sessions")
            tools = ToolRegistry(memory)
            agent = Agent(sessions, memory, tools)
            with patch.object(tools.computer, "list_apps", return_value={"apps": ["Spotify"], "count": 1}):
                response = agent.turn(None, "/computer apps")

        self.assertIn("Spotify", response["message"]["content"])
        self.assertEqual(response["tool_calls"][0]["name"], "computer_list_apps")

    def test_computer_type_command_allows_current_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp) / "vault")
            sessions = SessionStore(Path(tmp) / "sessions")
            tools = ToolRegistry(memory)
            agent = Agent(sessions, memory, tools)
            with patch.object(tools.computer, "type_text", return_value={"ok": True, "app": "Spotify"}):
                response = agent.turn(None, "/computer type Spotify :: Bollywood Acoustic")

        self.assertIn("Typed into", response["message"]["content"])
        self.assertEqual(response["tool_calls"][0]["input"]["element_path"], "")

    def test_runner_executes_model_planned_open_app(self):
        class FakeTools:
            def __init__(self):
                self.calls = []

            def call(self, name, **kwargs):
                self.calls.append((name, kwargs))
                outputs = {
                    "computer_list_apps": {"apps": []},
                    "computer_screenshot": {"ok": False, "error": "no screen"},
                    "computer_open_app": {"ok": True, "app": kwargs.get("app")},
                }
                return ToolResult.run(name, kwargs, outputs.get(name, {}))

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            def complete(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {"text": '{"status":"continue","message":"Opening Spotify","action":{"tool":"open_app","app":"Spotify","purpose":"open requested app"}}'}
                return {"text": '{"status":"done","message":"Spotify is open","action":{"tool":"wait"}}'}

        tools = FakeTools()
        answer, results = ComputerTaskRunner(tools, FakeLLM(), max_steps=2).run("open Spotify", {})

        self.assertEqual(answer, "Spotify is open")
        self.assertIn(("computer_open_app", {"app": "Spotify"}), tools.calls)
        self.assertTrue(any(result.name == "computer_open_app" for result in results))


if __name__ == "__main__":
    unittest.main()
