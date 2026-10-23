import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "roles/codex/files/browser-connect.py"
SPEC = importlib.util.spec_from_file_location("browser_connect", SOURCE)
hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hook)
SESSION = "11111111-1111-4111-8111-111111111111"
OTHER_SESSION = "22222222-2222-4222-8222-222222222222"


class BrowserServer:
    def __init__(self, path, session=SESSION, kind="iab", oversized=False):
        self.path, self.session, self.kind = path, session, kind
        self.oversized = oversized
        self.requests = []
        self.stop_event = threading.Event()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen()
        self.server.settimeout(0.05)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                client, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with client:
                try:
                    deadline = time.monotonic() + 1
                    size, = struct.unpack("=I", hook.recv_exact(client, 4, deadline))
                    request = json.loads(hook.recv_exact(client, size, deadline))
                    self.requests.append(request)
                    if self.oversized:
                        client.sendall(struct.pack("=I", hook.MAX_FRAME + 1))
                        continue
                    response = {"jsonrpc": "2.0", "id": request["id"], "result": {
                        "type": self.kind,
                        "metadata": {"codexSessionId": self.session},
                    }}
                    data = json.dumps(response).encode()
                    frame = struct.pack("=I", len(data)) + data
                    # Deliberately fragment both the header and the body.
                    client.sendall(frame[:2])
                    client.sendall(frame[2:11])
                    client.sendall(frame[11:])
                except (OSError, ValueError, ConnectionError):
                    pass

    def close(self):
        self.stop_event.set()
        self.server.close()
        self.thread.join(timeout=1)
        self.path.unlink(missing_ok=True)


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="iab-hook-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sockets = self.root / "sockets"
        self.sockets.mkdir()
        self.state = self.root / "state"
        self.launcher = self.root / "chatgpt"
        self.launcher.touch(mode=0o755)

    def server(self, name="browser.sock", **kwargs):
        server = BrowserServer(self.sockets / name, **kwargs)
        self.addCleanup(server.close)
        return server

    def connect(self, wait_seconds=1):
        return hook.ensure_connected(
            SESSION, "current-turn", socket_dir=self.sockets,
            state_dir=self.state, launcher=self.launcher, wait_seconds=wait_seconds,
        )

    def test_missing_desktop_skips_all_connection_work(self):
        with patch.object(hook, "find_launcher", return_value=None):
            with patch.object(hook, "discover") as discover:
                self.assertEqual(hook.ensure_connected(
                    SESSION, "turn", socket_dir=self.sockets, state_dir=self.state,
                ), "unavailable")
                discover.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_missing_or_non_executable_launcher_skips_immediately(self):
        self.launcher.chmod(0o644)
        with patch.object(hook, "discover") as discover:
            for launcher in (self.root / "missing", self.launcher):
                self.assertEqual(hook.ensure_connected(
                    SESSION, "turn", state_dir=self.state, launcher=launcher,
                ), "unavailable")
            discover.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_finds_official_or_community_desktop_but_not_codex_cli(self):
        with patch.object(hook.shutil, "which", return_value=str(self.launcher)) as which:
            self.assertEqual(hook.find_launcher(), self.launcher)
            which.assert_called_once_with("chatgpt")
        with patch.object(hook.shutil, "which", side_effect=[None, str(self.launcher)]) as which:
            self.assertEqual(hook.find_launcher(), self.launcher)
            self.assertEqual([call.args[0] for call in which.call_args_list],
                             ["chatgpt", "codex-desktop"])
        with patch.object(hook.shutil, "which", return_value=None):
            self.assertIsNone(hook.find_launcher())

    def test_handshake_handles_fragmented_frames_and_checks_identity(self):
        server = self.server()
        self.assertTrue(hook.probe(server.path, SESSION, "active-turn", 0.5))
        self.assertEqual(server.requests[0]["method"], "getInfo")
        self.assertEqual(server.requests[0]["params"], {
            "session_id": SESSION, "turn_id": "active-turn", "session_context": "live",
        })
        self.assertFalse(hook.probe(server.path, OTHER_SESSION, "active-turn", 0.5))

    def test_other_browser_types_and_oversized_frames_are_not_ready(self):
        extension = self.server("extension.sock", kind="extension")
        oversized = self.server("oversized.sock", oversized=True)
        self.assertFalse(hook.probe(extension.path, SESSION, "turn", 0.5))
        self.assertFalse(hook.probe(oversized.path, SESSION, "turn", 0.5))

    def test_ready_connection_does_not_launch_desktop(self):
        server = self.server()
        with patch.object(hook, "launch_desktop") as launch:
            self.assertEqual(self.connect(), "ready")
            self.assertEqual(self.connect(), "ready")
            launch.assert_not_called()
        self.assertEqual((self.state / f"{SESSION}.socket").read_text(), str(server.path))

    def test_launch_waits_for_connection(self):
        process = Mock()
        process.poll.return_value = None
        def launch(session_id, launcher):
            self.assertEqual(session_id, SESSION)
            timer = threading.Timer(0.1, self.server)
            timer.start()
            self.addCleanup(timer.join)
            return process
        with patch.object(hook, "launch_desktop", side_effect=launch) as launch_mock:
            self.assertEqual(self.connect(), "connected")
            launch_mock.assert_called_once()
        process.wait.assert_not_called()

    def test_parallel_calls_launch_only_once(self):
        process = Mock()
        process.poll.return_value = None
        def launch(*_):
            time.sleep(0.05)
            self.server()
            return process
        with patch.object(hook, "launch_desktop", side_effect=launch) as launch_mock:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.connect) for _ in range(2)]
                results = [future.result() for future in futures]
        self.assertCountEqual(results, ["connected", "ready"])
        launch_mock.assert_called_once()

    def test_stale_cache_is_replaced_after_desktop_restart(self):
        old = self.server("old.sock")
        self.connect()
        old.close()
        current = self.server("new.sock")
        with patch.object(hook, "launch_desktop") as launch:
            self.assertEqual(self.connect(), "ready")
            launch.assert_not_called()
        self.assertEqual((self.state / f"{SESSION}.socket").read_text(), str(current.path))

    def test_missing_registration_has_bounded_timeout(self):
        process = Mock()
        process.poll.return_value = None
        start = time.monotonic()
        with patch.object(hook, "launch_desktop", return_value=process):
            with self.assertRaisesRegex(hook.ConnectionFailure, "did not register"):
                self.connect(wait_seconds=0.12)
        self.assertLess(time.monotonic() - start, 0.6)

    def test_failed_launcher_returns_actionable_error(self):
        process = Mock()
        process.poll.return_value = 7
        with patch.object(hook, "launch_desktop", return_value=process):
            with self.assertRaisesRegex(hook.ConnectionFailure, "status 7"):
                self.connect()

    def test_socket_symlink_is_not_used(self):
        server = self.server()
        alias = self.sockets / "alias.sock"
        alias.symlink_to(server.path)
        self.assertFalse(hook.owned_socket(alias, self.sockets))

    def test_launcher_uses_fixed_executable_and_argument_list(self):
        with patch.object(hook.subprocess, "Popen") as popen:
            hook.launch_desktop(SESSION, self.launcher)
        self.assertEqual(popen.call_args.args[0], [str(self.launcher), f"codex://threads/{SESSION}"])
        self.assertNotIn("shell", popen.call_args.kwargs)

    def run_main(self, event):
        output = io.StringIO()
        with patch.object(hook.sys, "stdin", io.StringIO(json.dumps(event))):
            with contextlib.redirect_stdout(output):
                hook.main()
        return output.getvalue()

    def test_hook_ignores_unrelated_tools(self):
        with patch.object(hook, "ensure_connected") as connect:
            self.assertEqual(self.run_main({"hook_event_name": "PreToolUse", "tool_name": "Bash"}), "")
            connect.assert_not_called()

    def test_hook_uses_ids_from_event_without_approving_tool(self):
        with patch.object(hook, "ensure_connected") as connect:
            self.assertEqual(self.run_main({
                "hook_event_name": "PreToolUse", "tool_name": hook.TOOL_NAME,
                "session_id": SESSION, "turn_id": "real-current-turn",
            }), "")
            connect.assert_called_once_with(SESSION, "real-current-turn")

    def test_invalid_session_cannot_be_used_in_a_deep_link(self):
        with patch.object(hook, "ensure_connected") as connect:
            result = self.run_main({
                "hook_event_name": "PreToolUse", "tool_name": hook.TOOL_NAME,
                "session_id": "../settings?change=true", "turn_id": "current-turn",
            })
            self.assertEqual(result, "")
            connect.assert_not_called()

    def test_all_preparation_errors_fail_open_without_overriding_policy(self):
        event = {"hook_event_name": "PreToolUse", "tool_name": hook.TOOL_NAME,
                 "session_id": SESSION, "turn_id": "current-turn"}
        for error in (hook.ConnectionFailure("Desktop missing"),
                      hook.ConnectionFailure("registration timed out"),
                      PermissionError("cache is read-only"),
                      RuntimeError("unexpected failure")):
            with self.subTest(error=error):
                with patch.object(hook, "ensure_connected", side_effect=error):
                    self.assertEqual(self.run_main(event), "")

    def test_malformed_hook_input_fails_open(self):
        for raw in ("not json", "[]", "{}", "x" * (hook.MAX_FRAME + 1)):
            with patch.object(hook.sys, "stdin", io.StringIO(raw)):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    hook.main()
                self.assertEqual(output.getvalue(), "")

    def test_cli_without_desktop_exits_successfully_without_cache(self):
        # The real entry point must be harmless on headless/CLI-only hosts.
        import subprocess
        import sys
        event = {"hook_event_name": "PreToolUse", "tool_name": hook.TOOL_NAME,
                 "session_id": SESSION, "turn_id": "current-turn"}
        result = subprocess.run(
            [sys.executable, str(SOURCE)], input=json.dumps(event),
            env={**os.environ, "PATH": str(self.root / "no-desktop"),
                 "XDG_CACHE_HOME": str(self.root / "cache")},
            text=True, capture_output=True, timeout=2, check=True,
        )
        self.assertEqual((result.stdout, result.stderr), ("", ""))
        self.assertFalse((self.root / "cache").exists())


if __name__ == "__main__":
    unittest.main()
