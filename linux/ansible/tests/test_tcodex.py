"""Exercise a real nested PTY, with a tiny terminal emulator and a fake Codex."""

import errno
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "roles/wsl/files/tcodex.py"
spec = importlib.util.spec_from_file_location("tcodex", SOURCE)
tcodex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcodex)


PRELUDE = """#!/usr/bin/env python3
import fcntl,json,os,signal,struct,sys,termios,time,tty
def size():
    return struct.unpack('HHHH', fcntl.ioctl(0,termios.TIOCGWINSZ,b'\\0'*8))
def emit(label):
    print(label+json.dumps(size()),flush=True)
"""


class Terminal:
    def __init__(self, body, *, cell=(8, 16), native=(0, 0), reply=True, args=()):
        self.temp = tempfile.TemporaryDirectory()
        executable = Path(self.temp.name) / "codex"
        executable.write_text(PRELUDE + body)
        executable.chmod(0o755)
        self.master, self.slave = pty.openpty()
        tcodex.set_size(self.slave, (24, 80, *native))
        self.attrs = termios.tcgetattr(self.slave)
        self.cell = cell
        self.reply = reply
        self.queries = []
        self.output = bytearray()
        self.pending = bytearray()
        self.closed = False
        env = dict(os.environ, PATH=self.temp.name + os.pathsep + os.environ["PATH"])
        env.pop("TCODEX_ACTIVE", None)

        def controlling_terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen(
            [sys.executable, str(SOURCE), *args],
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            env=env,
            # Single-threaded harness: the slave must become a controlling TTY
            # so kernel window changes really deliver SIGWINCH to the wrapper.
            preexec_fn=controlling_terminal,  # noqa: PLW1509
        )

    def pump(self, timeout=0.1):
        if not select.select([self.master], [], [], timeout)[0]:
            return
        try:
            data = os.read(self.master, 65536)
        except OSError as error:
            if error.errno != errno.EIO:
                raise
            return
        self.pending.extend(data)
        while self.pending:
            if self.pending.startswith(b"\x1b[16t") or self.pending.startswith(
                b"\x1b[14t"
            ):
                query = bytes(self.pending[:5])
                del self.pending[:5]
                self.queries.append(query)
                if self.reply:
                    if query == b"\x1b[16t" and self.reply != "area-only":
                        width, height = self.cell
                        self.send(f"\x1b[6;{height};{width}t".encode())
                    elif query == b"\x1b[14t":
                        rows, cols, _, _ = tcodex.get_size(self.slave)
                        self.send(
                            f"\x1b[4;{rows * self.cell[1]};{cols * self.cell[0]}t".encode()
                        )
                continue
            if any(q.startswith(self.pending) for q in (b"\x1b[16t", b"\x1b[14t")):
                break
            next_escape = self.pending.find(b"\x1b", 1)
            length = next_escape if next_escape >= 0 else len(self.pending)
            self.output.extend(self.pending[:length])
            del self.pending[:length]

    def wait_for(self, text, timeout=4):
        end = time.monotonic() + timeout
        while text not in self.output:
            if time.monotonic() > end:
                raise AssertionError(
                    f"missing {text!r}; output={bytes(self.output[-1000:])!r}"
                )
            self.pump(0.02)
        return bytes(self.output)

    def send(self, data):
        tcodex.write_all(self.master, data)

    def resize(self, rows, cols, cell=None):
        if cell:
            self.cell = cell
        tcodex.set_size(self.slave, (rows, cols, 0, 0))

    def finish(self, timeout=4):
        end = time.monotonic() + timeout
        while self.process.poll() is None:
            if time.monotonic() > end:
                raise AssertionError("wrapper did not exit")
            self.pump(0.02)
        for _ in range(3):
            self.pump(0.01)
        if self.attrs != termios.tcgetattr(self.slave):
            raise AssertionError("outer terminal attributes were not restored")
        return self.process.returncode

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            os.kill(self.process.pid, signal.SIGCONT)
            self.process.terminate()
            try:
                self.finish()
            except (AssertionError, ProcessLookupError):
                self.process.kill()
                self.process.wait(timeout=2)
        os.close(self.master)
        os.close(self.slave)
        self.temp.cleanup()


class InputTests(unittest.TestCase):
    def test_fragmented_reply_and_utf8_input(self):
        decoder = tcodex.Input()
        decoder.expected = 6
        actual, reports = bytearray(), []
        for byte in "до\x1b[6;24;12tпосле\x1b[A".encode():
            forwarded, found = decoder.feed(bytes([byte]))
            actual.extend(forwarded)
            reports.extend(found)
        actual.extend(decoder.flush())
        self.assertEqual(actual, "допосле\x1b[A".encode())
        self.assertEqual(reports, [(6, 24, 12)])

    def test_bracketed_paste_is_never_a_report(self):
        decoder = tcodex.Input()
        decoder.expected = 6
        pasted = b"\x1b[200~\x1b[6;24;12t\x1b[201~"
        output = bytearray()
        reports = []
        for byte in pasted + b"\x1b[6;16;8t":
            chunk, found = decoder.feed(bytes([byte]))
            output.extend(chunk)
            reports.extend(found)
        self.assertEqual(output, pasted)
        self.assertEqual(reports, [(6, 16, 8)])

    def test_other_queries_and_keys_are_preserved(self):
        decoder = tcodex.Input()
        decoder.expected = 6
        value = b"\x1b[4;123;456t\x1b]11;rgb:ffff/ffff/ffff\x1b\\\x1b[1;5A\x1b[97;5u"
        output, reports = decoder.feed(value)
        self.assertEqual(output, value)
        self.assertEqual(reports, [])


class PTYTests(unittest.TestCase):
    def terminal(self, body, **kwargs):
        terminal = Terminal(body, **kwargs)
        self.addCleanup(terminal.close)
        return terminal

    def test_initial_cell_size_arguments_and_exit_status(self):
        terminal = self.terminal(
            """tty.setraw(0)
emit('SIZE=')
print('ARGS='+json.dumps(sys.argv[1:]),flush=True)
sys.exit(23)
""",
            args=["resume", "a b", "--image", "картинка.png"],
        )
        self.assertEqual(terminal.finish(), 23)
        self.assertIn(b"SIZE=[24, 80, 640, 384]", terminal.output)
        self.assertIn(
            json.dumps(["resume", "a b", "--image", "картинка.png"]).encode(),
            terminal.output,
        )

    def test_area_query_fallback(self):
        terminal = self.terminal("tty.setraw(0)\nemit('SIZE=')\n", reply="area-only")
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(b"SIZE=[24, 80, 640, 384]", terminal.output)
        self.assertEqual(terminal.queries, [b"\x1b[16t", b"\x1b[14t"])

    def test_unsupported_terminal_still_runs(self):
        terminal = self.terminal("tty.setraw(0)\nemit('SIZE=')\n", reply=False)
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(b"SIZE=[24, 80, 0, 0]", terminal.output)

    def test_native_pixels_are_preserved_without_startup_query(self):
        terminal = self.terminal("tty.setraw(0)\nemit('SIZE=')\n", native=(800, 480))
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(b"SIZE=[24, 80, 800, 480]", terminal.output)
        self.assertEqual(terminal.queries, [])

    def test_resize_and_changed_font_size(self):
        terminal = self.terminal("""tty.setraw(0)
signal.signal(signal.SIGWINCH,lambda *_: emit('SIZE='))
emit('READY=')
while os.read(0,1024) != b'q': pass
""")
        terminal.wait_for(b"READY=[24, 80, 640, 384]")
        terminal.resize(40, 120)
        terminal.wait_for(b"SIZE=[40, 120, 960, 640]")
        terminal.resize(30, 90, cell=(12, 24))
        terminal.wait_for(b"SIZE=[30, 90, 1080, 720]")
        terminal.send(b"q")
        self.assertEqual(terminal.finish(), 0)

    def test_query_reply_does_not_enter_child_input(self):
        terminal = self.terminal("""tty.setraw(0)
emit('READY=')
value=bytearray()
while b'END' not in value: value.extend(os.read(0,65536))
print('INPUT='+value.hex(),flush=True)
""")
        terminal.wait_for(b"READY=")
        terminal.resize(30, 90)
        end = time.monotonic() + 2
        while len(terminal.queries) < 2 and time.monotonic() < end:
            terminal.pump(0.02)
        self.assertEqual(len(terminal.queries), 2)
        data = "текст\x1b[200~\x1b[6;1;2t\x1b[201~\x1b[AEND".encode()
        terminal.send(data)
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(("INPUT=" + data.hex()).encode(), terminal.output)

    def test_keystrokes_during_initial_probe_are_preserved(self):
        terminal = self.terminal(
            """tty.setraw(0)
emit('READY=')
print('INPUT='+os.read(0,3).hex(),flush=True)
""",
            reply=False,
        )
        end = time.monotonic() + 2
        while not terminal.queries and time.monotonic() < end:
            terminal.pump(0.02)
        terminal.send(b"abc\x1b[6;16;8t")
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(b"INPUT=616263", terminal.output)

    def test_large_output_and_sixel_are_not_modified(self):
        terminal = self.terminal("""tty.setraw(0)
payload=b'\\x1bP0;1q#0;2;100;0;0~\\x1b\\\\'+b'x'*1500000
while payload:
    length=os.write(1,payload)
    payload=payload[length:]
""")
        self.assertEqual(terminal.finish(), 0)
        self.assertEqual(
            terminal.output, b"\x1bP0;1q#0;2;100;0;0~\x1b\\" + b"x" * 1500000
        )

    def test_ctrl_c_reaches_foreground_child(self):
        terminal = self.terminal("""tty.setcbreak(0)
signal.signal(signal.SIGINT,lambda *_: sys.exit(42))
emit('READY=')
time.sleep(60)
""")
        terminal.wait_for(b"READY=")
        terminal.send(b"\x03")
        self.assertEqual(terminal.finish(), 42)

    def test_external_signal_and_restoration(self):
        terminal = self.terminal("tty.setraw(0)\nemit('READY=')\ntime.sleep(60)\n")
        terminal.wait_for(b"READY=")
        terminal.process.terminate()
        self.assertEqual(terminal.finish(), 128 + signal.SIGTERM)

    def test_signal_during_startup_probe_restores_terminal(self):
        terminal = self.terminal("emit('SHOULD_NOT_START=')\n", reply=False)
        deadline = time.monotonic() + 2
        while not terminal.queries and time.monotonic() < deadline:
            terminal.pump(0.02)
        self.assertTrue(terminal.queries)
        terminal.process.terminate()
        self.assertEqual(terminal.finish(), 128 + signal.SIGTERM)
        self.assertNotIn(b"SHOULD_NOT_START=", terminal.output)

    def test_resize_does_not_split_an_image_escape_string(self):
        terminal = self.terminal("""tty.setraw(0)
emit('READY=')
os.read(0,1)
os.write(1,b'\\x1bPqIMAGE_START')
os.read(0,1)
os.write(1,b'IMAGE_END\\x1b\\\\')
os.read(0,1)
""")
        terminal.wait_for(b"READY=")
        terminal.send(b"a")
        terminal.wait_for(b"IMAGE_START")
        terminal.resize(30, 90)
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            terminal.pump(0.02)
        self.assertEqual(len(terminal.queries), 1)
        terminal.send(b"b")
        deadline = time.monotonic() + 2
        while len(terminal.queries) < 2 and time.monotonic() < deadline:
            terminal.pump(0.02)
        self.assertEqual(len(terminal.queries), 2)
        terminal.send(b"q")
        self.assertEqual(terminal.finish(), 0)
        self.assertIn(b"\x1bPqIMAGE_STARTIMAGE_END\x1b\\", terminal.output)

    def test_suspend_resume_restores_terminal_and_resizes(self):
        terminal = self.terminal("""tty.setraw(0)
emit('READY=')
os.read(0,1)
os.kill(os.getpid(),signal.SIGSTOP)
emit('RESUMED=')
""")
        terminal.wait_for(b"READY=")
        terminal.send(b"z")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = Path(f"/proc/{terminal.process.pid}/status").read_text()
            if re.search(r"^State:\s+T", state, re.MULTILINE):
                break
            terminal.pump(0.02)
        else:
            self.fail("wrapper did not suspend")
        self.assertEqual(termios.tcgetattr(terminal.slave), terminal.attrs)
        terminal.resize(30, 90)
        os.kill(terminal.process.pid, signal.SIGCONT)
        self.assertEqual(terminal.finish(), 0)
        terminal.wait_for(b"RESUMED=")


class BinaryPatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "package/bin/codex"
        self.source.parent.mkdir(parents=True)
        self.before = b"\x7fELF" + b"\0" * 12 + bytes.fromhex("06000300") + b"\0" * 40
        self.after = self.before[:16] + bytes.fromhex("0c000600") + self.before[20:]
        self.source.write_bytes(self.before)
        self.source.chmod(0o755)
        (self.source.parent / "codex-code-mode-host").write_text("helper")
        (self.source.parent.parent / "codex-package.json").write_text("{}")
        (self.source.parent.parent / "codex-resources").mkdir()
        (self.source.parent.parent / "codex-path").mkdir()
        self.cache = self.root / "cache"
        self.enterContext(
            mock.patch.object(
                tcodex, "PREVIEW_SOURCE_SHA256", hashlib.sha256(self.before).hexdigest()
            )
        )
        self.enterContext(
            mock.patch.object(
                tcodex, "PREVIEW_PATCHED_SHA256", hashlib.sha256(self.after).hexdigest()
            )
        )
        self.enterContext(
            mock.patch.object(
                tcodex, "PREVIEW_EDITS", ((0x1010, "06000300", "0c000600"),)
            )
        )

    def prepare(self):
        return Path(tcodex.preview_binary(self.source, self.cache))

    def test_private_copy_preserves_package_and_reuses_cached_binary(self):
        target = self.prepare()
        self.assertEqual(target.read_bytes(), self.after)
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertTrue(os.access(target, os.X_OK))
        snapshot = target.stat()
        self.assertEqual(self.prepare(), target)
        self.assertEqual(target.stat().st_ino, snapshot.st_ino)
        self.assertEqual(target.stat().st_mtime_ns, snapshot.st_mtime_ns)
        self.assertEqual(
            (target.parent / "codex-code-mode-host").resolve(),
            self.source.parent / "codex-code-mode-host",
        )
        for name in ("codex-package.json", "codex-resources", "codex-path"):
            self.assertEqual(
                (target.parent.parent / name).resolve(),
                self.source.parent.parent / name,
            )

    def test_unknown_build_does_not_create_cache_or_change_binary(self):
        changed = self.before + b"new build"
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "unsupported Codex build"):
            self.prepare()
        self.assertEqual(self.source.read_bytes(), changed)
        self.assertFalse(self.cache.exists())

    def test_wrong_instruction_is_rejected_before_publishing(self):
        with (
            mock.patch.object(
                tcodex, "PREVIEW_EDITS", ((0x1010, "07000300", "0c000600"),)
            ),
            self.assertRaisesRegex(ValueError, "unexpected preview instruction"),
        ):
            self.prepare()
        self.assertFalse(self.cache.exists())

    def test_incorrect_result_checksum_is_not_published(self):
        with (
            mock.patch.object(tcodex, "PREVIEW_PATCHED_SHA256", "0" * 64),
            self.assertRaisesRegex(ValueError, "checksum mismatch"),
        ):
            self.prepare()
        self.assertEqual(list(self.cache.glob("*/bin/codex")), [])
        self.assertEqual(list(self.cache.glob("*/bin/.codex-*")), [])

    def test_corrupted_cache_is_rebuilt_without_touching_installed_binary(self):
        target = self.prepare()
        target.write_bytes(b"corrupt cache")
        self.assertEqual(self.prepare().read_bytes(), self.after)
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_concurrent_launches_publish_one_complete_binary(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: self.prepare(), range(3)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(results[0].read_bytes(), self.after)
        self.assertEqual(list(self.cache.glob("*/bin/.codex-*")), [])

    def test_existing_patch_and_script_launcher_are_left_as_is(self):
        self.source.write_bytes(self.after)
        self.assertEqual(self.prepare(), self.source)
        self.assertFalse(self.cache.exists())
        script = self.root / "launcher"
        script.write_text('#!/bin/sh\nexec codex "$@"\n')
        link = self.root / "codex-link"
        link.symlink_to(script)
        self.assertEqual(tcodex.preview_binary(link, self.cache), str(link))
        self.assertFalse(self.cache.exists())

    def test_maintenance_commands_are_not_patched(self):
        for args in (
            ["update"],
            ["--cd", "somewhere", "update"],
            ["exec", "--json"],
            ["completion", "fish"],
        ):
            self.assertFalse(tcodex.wants_preview_patch(args), args)
        for args in (
            [],
            ["resume", "--last"],
            ["--cd", "update", "resume"],
            ["--", "update"],
        ):
            self.assertTrue(tcodex.wants_preview_patch(args), args)

    def test_launch_falls_back_on_unsupported_build(self):
        self.enterContext(mock.patch.dict(os.environ, {"TCODEX_PREVIEW_PATCH": "1"}))
        self.enterContext(mock.patch.object(sys, "argv", ["tcodex"]))
        self.enterContext(mock.patch.object(tcodex, "interactive", return_value=True))
        self.enterContext(
            mock.patch.object(tcodex.shutil, "which", return_value=str(self.source))
        )
        self.enterContext(
            mock.patch.object(
                tcodex, "preview_binary", side_effect=ValueError("unsupported build")
            )
        )
        run = self.enterContext(mock.patch.object(tcodex, "run", return_value=0))
        stderr = self.enterContext(mock.patch.object(sys, "stderr", io.StringIO()))
        self.assertEqual(tcodex.main(), 0)
        run.assert_called_once_with(["codex"])
        self.assertIn("using installed Codex", stderr.getvalue())

    def test_launch_preserves_arguments_and_empty_xdg_cache_uses_home(self):
        args = ["--cd", "update", "resume", "--last"]
        self.enterContext(mock.patch.object(sys, "argv", ["tcodex", *args]))
        self.enterContext(mock.patch.object(tcodex, "interactive", return_value=True))
        self.enterContext(
            mock.patch.object(tcodex.shutil, "which", return_value=str(self.source))
        )
        self.enterContext(
            mock.patch.dict(
                os.environ, {"TCODEX_PREVIEW_PATCH": "1", "XDG_CACHE_HOME": ""}
            )
        )
        self.enterContext(mock.patch.object(Path, "home", return_value=self.root))
        prepare = self.enterContext(
            mock.patch.object(tcodex, "preview_binary", return_value="/cache/bin/codex")
        )
        run = self.enterContext(mock.patch.object(tcodex, "run", return_value=0))
        self.assertEqual(tcodex.main(), 0)
        prepare.assert_called_once_with(str(self.source), self.root / ".cache/tcodex")
        run.assert_called_once_with(["/cache/bin/codex", *args])

    def test_disabled_patch_and_noninteractive_launch_do_not_prepare_a_copy(self):
        self.enterContext(
            mock.patch.object(sys, "argv", ["tcodex", "resume", "--last"])
        )
        prepare = self.enterContext(mock.patch.object(tcodex, "preview_binary"))
        run = self.enterContext(mock.patch.object(tcodex, "run", return_value=0))
        for is_interactive, disabled in ((True, "0"), (False, "1")):
            with (
                mock.patch.object(tcodex, "interactive", return_value=is_interactive),
                mock.patch.dict(os.environ, {"TCODEX_PREVIEW_PATCH": disabled}),
            ):
                self.assertEqual(tcodex.main(), 0)
                run.assert_called_with(["codex", "resume", "--last"])
        prepare.assert_not_called()


class PipelineTests(unittest.TestCase):
    def test_pipeline_preserves_stdin_stdout_stderr_arguments_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "codex"
            command.write_text(
                PRELUDE
                + """sys.stdout.buffer.write(sys.stdin.buffer.read())
sys.stderr.write(json.dumps(sys.argv[1:]))
sys.exit(19)
"""
            )
            command.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"])
            result = subprocess.run(
                [sys.executable, str(SOURCE), "exec", "a b"],
                input=b"\x00\xff\n",
                capture_output=True,
                env=env,
                timeout=3,
                check=False,
            )
            self.assertEqual(result.returncode, 19)
            self.assertEqual(result.stdout, b"\x00\xff\n")
            self.assertEqual(json.loads(result.stderr), ["exec", "a b"])


@unittest.skipUnless(shutil.which("fish"), "fish is not installed")
class FishTests(unittest.TestCase):
    def test_inherits_options_subcommands_values_and_paths(self):
        completion = SOURCE.with_name("tcodex.fish")
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "codex.fish"
            fake.write_text("""complete -c codex -l model -r -f -a 'one two'
complete -c codex -l image -r -F
complete -c codex -a 'resume exec'
complete -c codex -n 'contains resume (commandline -opc)' -l last
""")
            (Path(tmp) / "sample image.png").touch()
            script = """source $argv[1]
source $argv[2]
for suffix in '--' 'resume --' '--model ' '--image '
    set -l direct (complete -C "codex $suffix")
    set -l wrapped (complete -C "tcodex $suffix")
    test (count $direct) -gt 0; or exit 1
    test "$direct" = "$wrapped"; or exit 2
end
"""
            result = subprocess.run(
                ["fish", "--no-config", "-c", script, str(fake), str(completion)],
                capture_output=True,
                text=True,
                cwd=tmp,
                timeout=3,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
