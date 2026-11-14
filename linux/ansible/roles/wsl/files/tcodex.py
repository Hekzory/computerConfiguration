#!/usr/bin/env python3
"""Run Codex in a PTY whose pixel geometry follows the outer terminal.

WSL supplies rows/columns but leaves TIOCGWINSZ pixel dimensions at zero.
Query XTWINOPS 16 (cell pixels), falling back to 14 (text area pixels).
An input relay keeps these replies out of Codex, including during resizes.
For a verified Codex build, a persistent private binary copy doubles draft
thumbnail dimensions to 12x6 cells. Unknown builds run without this patch.
Uses only the Python standard library.
"""

import errno
import fcntl
import hashlib
import mmap
import os
import pty
import re
import select
import shutil
import signal
import struct
import sys
import tempfile
import termios
import time
import tty
from pathlib import Path

QUERY_TIMEOUT = 0.25
ESC_TIMEOUT = 0.04
QUEUE_LIMIT = 1024 * 1024
PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"
REPORT = re.compile(rb"\x1b\[([46]);([0-9]{1,5});([0-9]{1,5})t")
REPORT_PREFIX = re.compile(rb"\x1b\[(?:[46](?:;[0-9]{0,5}){0,2})?")

# Arch openai-codex 0.169.0+arch.1.1, x86_64-unknown-linux-gnu.
# Full-file hashes pin the compiler output, not just the displayed version.
PREVIEW_SOURCE_SHA256 = (
    "6beb0eda4e70a9ecd89840193de4093780ce27dba3a925ecd9854d06f1fc0e4f"
)
PREVIEW_PATCHED_SHA256 = (
    "0dc875a24f8fe6438633d75c2a61dd699766ad8b0104a5ae6ddddb843fc343db"
)
# .text virtual addresses; this ELF's file offsets are address - 0x1000.
# Besides raster dimensions, update layout, clipping, placement and badge math.
# Double the raster budgets too, retaining the original supported cell sizes.
PREVIEW_EDITS = (
    (0xFF7837A, "4c69c925499224", "4c69c9143bb113"),  # render: divide by 13
    (0xFF7839D, "4a8d3ccd00000000", "496bf90d90909090"),  # visible width *13
    (0xFF783C9, "4c29cf", "909090"),  # multiplication already complete
    (0xFF783D2, "4883c709", "4883c70f"),  # hidden badge offset
    (0xFF7844B, "4a8d541ff9", "4a8d541ff3"),  # hidden badge spacing
    (0xFF7845E, "4883c7f9", "4883c7f3"),  # hide one tile
    (0x100148C8, "4869d125499224", "4869d1143bb113"),  # layout: divide by 13
    (0x100148ED, "4c8d0cd500000000", "4c6bca0d90909090"),  # visible width *13
    (0x10014926, "4929d1", "909090"),  # multiplication already complete
    (0x10014929, "4983c109", "4983c10f"),  # hidden badge offset
    (0x10014991, "498d5431f9", "498d5431f3"),  # hidden badge spacing
    (0x100149A8, "4983c1f9", "4983c1f3"),  # hide one tile
    (0x100149C5, "66b90400", "66b90700"),  # six rows plus gap
    (0x10014A6E, "66b90400", "66b90700"),  # six rows plus gap, badge path
    (0xFF78EE3, "6683c003", "6683c006"),  # tile rectangle height
    (0xFF79166, "438d3c5b", "416bfb06"),  # six times cell height
    (0xFF7916A, "8d0449", "6bc106"),  # twelve times cell width
    (0xFF79180, "48c1ea28", "48c1ea29"),  # doubled width budget
    (0xFF791A1, "48c1e927", "48c1e928"),  # doubled height budget
    (0xFF794F3, "c7434006000300", "c743400c000600"),  # columns and rows
    (0xFF795B0, "6683c306", "6683c30c"),  # tile rectangle width
    (0xFF79829, "664183c607", "664183c60d"),  # advance twelve columns plus gap
)


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preview_binary(executable, cache_root):
    """Build/reuse a checked private copy. Never write to the installed package."""
    source = Path(executable).resolve(strict=True)
    with source.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            return str(executable)  # Preserve npm/shell launcher invocation paths.
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
            digest = hashlib.sha256(image).hexdigest()
            if digest == PREVIEW_PATCHED_SHA256:
                return str(source)
            if digest != PREVIEW_SOURCE_SHA256:
                raise ValueError(f"unsupported Codex build {digest[:12]}")
            for address, before, after in PREVIEW_EDITS:
                before, after = bytes.fromhex(before), bytes.fromhex(after)
                offset = address - 0x1000
                if (
                    len(before) != len(after)
                    or image[offset : offset + len(before)] != before
                ):
                    raise ValueError(f"unexpected preview instruction at {address:#x}")

        cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Serialize concurrent launches and atomically publish only a complete file.
        with (cache_root / ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            origin = hashlib.sha256(os.fsencode(source)).hexdigest()[:12]
            package = cache_root / f"previews-12x6-v1-{origin}-{digest[:16]}"
            binary_dir = package / "bin"
            binary_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = binary_dir / "codex"
            valid = target.is_file() and file_digest(target) == PREVIEW_PATCHED_SHA256
            if not valid:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=binary_dir, prefix=".codex-", delete=False
                    ) as out:
                        temporary = Path(out.name)
                        stream.seek(0)
                        shutil.copyfileobj(stream, out, length=1024 * 1024)
                        for address, _, after in PREVIEW_EDITS:
                            out.seek(address - 0x1000)
                            out.write(bytes.fromhex(after))
                        out.flush()
                        os.fsync(out.fileno())
                        os.fchmod(out.fileno(), 0o700)
                    if file_digest(temporary) != PREVIEW_PATCHED_SHA256:
                        raise ValueError("patched Codex checksum mismatch")
                    os.replace(temporary, target)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)

            # Preserve current_exe-relative helper/resource lookup for this package.
            links = [
                (item, binary_dir / item.name)
                for item in source.parent.iterdir()
                if item.name != source.name
            ]
            if (source.parent.parent / "codex-package.json").is_file():
                links.extend(
                    (source.parent.parent / name, package / name)
                    for name in ("codex-package.json", "codex-resources", "codex-path")
                    if (source.parent.parent / name).exists()
                )
            for origin_path, link in links:
                if link.is_symlink() and os.readlink(link) == str(origin_path):
                    continue
                if link.exists() or link.is_symlink():
                    raise ValueError(f"unexpected file in preview cache: {link.name}")
                link.symlink_to(origin_path)
            return str(target)


def wants_preview_patch(argv):
    """Leave maintenance/server commands on the installed executable."""
    values = {
        "-c",
        "--config",
        "--enable",
        "--disable",
        "--remote",
        "--remote-auth-token-env",
        "-i",
        "--image",
        "-m",
        "--model",
        "--local-provider",
        "-p",
        "--profile",
        "-s",
        "--sandbox",
        "-C",
        "--cd",
        "--add-dir",
        "-a",
        "--ask-for-approval",
    }
    commands = {
        "exec",
        "e",
        "review",
        "login",
        "logout",
        "mcp",
        "plugin",
        "app-server",
        "remote-control",
        "completion",
        "update",
        "doctor",
        "sandbox",
        "debug",
        "execpolicy",
        "apply",
        "a",
        "queue",
        "archive",
        "delete",
        "migrate-rollouts",
        "migrate-nfs-db",
        "unarchive",
        "responses-api-proxy",
        "stdio-to-uds",
        "exec-server",
        "tcp-tunnel",
        "git-credential",
    }
    args = iter(argv)
    for arg in args:
        if arg == "--":
            return True
        if arg in values:
            next(args, None)
        elif not arg.startswith("-"):
            return arg not in commands
    return True


def interactive(command):
    return (
        all(os.isatty(fd) for fd in (0, 1, 2))
        and len({os.fstat(fd).st_rdev for fd in (0, 1, 2)}) == 1
        and not os.environ.get("TCODEX_ACTIVE")
        and not any(arg in ("--help", "-h", "--version", "-V") for arg in command[1:])
    )


class Terminated(Exception):
    def __init__(self, signum):
        self.signum = signum


def get_size(fd):
    return struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))


def set_size(fd, size):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", *size))


class Geometry:
    def __init__(self, fd):
        self.fd = fd
        self.cell = None

    def size(self):
        rows, cols, width, height = get_size(self.fd)
        if rows and cols and width and height:
            self.cell = (width // cols, height // rows)
            return rows, cols, width, height
        if self.cell:
            width, height = cols * self.cell[0], rows * self.cell[1]
            if not (0 < width <= 65535 and 0 < height <= 65535):
                width = height = 0
        return rows, cols, width, height

    def accept(self, report):
        kind, height, width = report
        rows, cols, _, _ = get_size(self.fd)
        if kind == 4:
            if not rows or not cols:
                return False
            width, height = width // cols, height // rows
        if 0 < width <= 4096 and 0 < height <= 4096:
            self.cell = (width, height)
            return True
        return False


class Input:
    """Consume only our pending size reply; preserve other input byte for byte."""

    def __init__(self):
        self.buffer = bytearray()
        self.paste = False
        self.expected = None
        self.held_at = None

    def feed(self, data):
        self.buffer.extend(data)
        output = bytearray()
        reports = []
        while self.buffer:
            marker = PASTE_END if self.paste else PASTE_START
            if self.buffer.startswith(marker):
                output.extend(self.buffer[: len(marker)])
                del self.buffer[: len(marker)]
                self.paste = not self.paste
                continue
            if marker.startswith(self.buffer):
                break
            if not self.paste and self.expected is not None:
                match = REPORT.match(self.buffer)
                if match and int(match[1]) == self.expected:
                    reports.append(tuple(int(x) for x in match.groups()))
                    del self.buffer[: match.end()]
                    self.expected = None
                    continue
                if len(self.buffer) <= 22 and REPORT_PREFIX.fullmatch(self.buffer):
                    break
            # Fast path for ordinary text / image protocol replies.
            next_escape = self.buffer.find(b"\x1b", 1)
            length = next_escape if next_escape >= 0 else len(self.buffer)
            output.extend(self.buffer[:length])
            del self.buffer[:length]
        self.held_at = time.monotonic() if self.buffer else None
        return output, reports

    def flush(self):
        output = self.buffer[:]
        self.buffer.clear()
        self.held_at = None
        return output


class Output:
    """Never insert a query inside a child's split CSI / OSC / image string."""

    def __init__(self):
        self.state = "ground"
        self.osc = False

    def feed(self, data):
        for byte in data:
            if self.state == "ground":
                if byte == 27:
                    self.state = "escape"
            elif self.state == "escape":
                if byte == ord("["):
                    self.state = "csi"
                elif byte in b"]P_X^":
                    self.osc = byte == ord("]")
                    self.state = "string"
                elif not 0x20 <= byte <= 0x2F:
                    self.state = "ground"
            elif self.state == "csi":
                if 0x40 <= byte <= 0x7E:
                    self.state = "ground"
                elif byte == 27:
                    self.state = "escape"
            elif self.state == "string":
                if byte == 27:
                    self.state = "string_escape"
                elif byte == 7 and self.osc:
                    self.state = "ground"
            elif byte == ord("\\"):
                self.state = "ground"
            elif byte != 27:
                self.state = "string"


def write_all(fd, data):
    view = memoryview(data)
    while view:
        try:
            view = view[os.write(fd, view) :]
        except BlockingIOError:
            select.select([], [fd], [])


def initial_probe(fd, geometry, decoder):
    buffered = bytearray()
    if all(geometry.size()):
        return buffered
    for kind, query in ((6, b"\x1b[16t"), (4, b"\x1b[14t")):
        decoder.expected = kind
        write_all(fd, query)
        deadline = time.monotonic() + QUERY_TIMEOUT
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            data = os.read(fd, 65536)
            if not data:
                raise OSError(errno.EIO, "terminal closed during size query")
            forwarded, reports = decoder.feed(data)
            buffered.extend(forwarded)
            if any(geometry.accept(report) for report in reports):
                buffered.extend(decoder.flush())
                return buffered
            if len(buffered) >= QUEUE_LIMIT or decoder.paste:
                break
        buffered.extend(decoder.flush())
        if len(buffered) >= QUEUE_LIMIT or decoder.paste:
            break
    decoder.expected = None
    return buffered


def foreground_signal(master, pid, signum):
    try:
        group = os.tcgetpgrp(master)
        os.killpg(group if group > 0 else pid, signum)
    except ProcessLookupError:
        pass


def relay(fd, master, pid, attrs, geometry, decoder, buffered):
    os.set_blocking(master, False)
    os.set_blocking(fd, False)
    to_child = bytearray(buffered)
    to_terminal = bytearray()
    wake_read, wake_write = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    old_wakeup = signal.set_wakeup_fd(wake_write)
    pending = set()
    handled = (
        signal.SIGWINCH,
        signal.SIGCHLD,
        signal.SIGCONT,
        signal.SIGHUP,
        signal.SIGTERM,
        signal.SIGINT,
        signal.SIGQUIT,
        signal.SIGTSTP,
    )
    old_handlers = {s: signal.getsignal(s) for s in handled}
    for signum in handled:
        signal.signal(signum, lambda s, _frame: pending.add(s))
    query_due = None
    query_deadline = None
    query_kind = 6
    status = None
    master_open = True
    output_state = Output()
    # A TUI may flush pending terminal input when it first enters raw mode.
    # Release typeahead after its first output, or after a short startup grace
    # for programs which read before writing anything.
    input_ready = not buffered
    input_ready_at = time.monotonic() + 0.1

    def resize():
        size = geometry.size()
        if get_size(master) != size:
            set_size(master, size)

    def suspend():
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        os.kill(os.getpid(), signal.SIGSTOP)
        tty.setraw(fd, termios.TCSANOW)
        foreground_signal(master, pid, signal.SIGCONT)
        resize()

    try:
        resize()
        while True:
            now = time.monotonic()
            if not input_ready and now >= input_ready_at:
                input_ready = True
            signals = pending.copy()
            pending.clear()
            for signum in signals:
                if signum == signal.SIGWINCH:
                    resize()
                    query_kind = 6
                    query_due = now + 0.05
                elif signum == signal.SIGCONT:
                    resize()
                    query_due = now
                elif signum == signal.SIGTSTP:
                    foreground_signal(master, pid, signal.SIGSTOP)
                elif signum != signal.SIGCHLD:
                    foreground_signal(master, pid, signum)

            if status is None:
                child, value = os.waitpid(pid, os.WNOHANG | os.WUNTRACED)
                if child:
                    if os.WIFSTOPPED(value):
                        suspend()
                        query_due = time.monotonic()
                    else:
                        status = value

            if decoder.buffer and now >= decoder.held_at + ESC_TIMEOUT:
                to_child.extend(decoder.flush())

            if query_deadline is not None and now >= query_deadline:
                to_child.extend(decoder.flush())
                if decoder.expected == 6 and not decoder.paste:
                    query_kind = 4
                    query_due = now
                decoder.expected = None
                query_deadline = None

            if (
                query_due is not None
                and now >= query_due
                and query_deadline is None
                and not decoder.paste
                and output_state.state == "ground"
            ):
                decoder.expected = query_kind
                to_terminal.extend(b"\x1b[16t" if query_kind == 6 else b"\x1b[14t")
                query_deadline = now + QUERY_TIMEOUT
                query_due = None

            reads = [wake_read]
            if len(to_child) < QUEUE_LIMIT and status is None:
                reads.append(fd)
            if master_open and len(to_terminal) < QUEUE_LIMIT:
                reads.append(master)
            writes = [fd] if to_terminal else []
            if to_child and input_ready and master_open and status is None:
                writes.append(master)
            deadlines = [
                x
                for x in (
                    query_deadline,
                    query_due
                    if not decoder.paste and output_state.state == "ground"
                    else None,
                    decoder.held_at + ESC_TIMEOUT if decoder.buffer else None,
                )
                if x is not None
            ]
            if not input_ready:
                deadlines.append(input_ready_at)
            timeout = max(0, min(deadlines) - now) if deadlines else None
            # Drain the exited child's remaining output, without waiting for descendants
            # that inherited its terminal. Ordinary output remains byte-for-byte intact.
            if status is not None and not to_terminal:
                timeout = 0
            readable, writable, _ = select.select(reads, writes, [], timeout)
            if status is not None and not to_terminal and master not in readable:
                return os.waitstatus_to_exitcode(status)
            for ready in readable:
                if ready == wake_read:
                    while True:
                        try:
                            if not os.read(wake_read, 4096):
                                break
                        except BlockingIOError:
                            break
                else:
                    try:
                        data = os.read(ready, 65536)
                    except BlockingIOError:
                        continue
                    except OSError as error:
                        if ready != master or error.errno != errno.EIO:
                            raise
                        data = b""
                    if ready == master:
                        if data:
                            input_ready = True
                            output_state.feed(data)
                            to_terminal.extend(data)
                        else:
                            master_open = False
                    elif not data:
                        foreground_signal(master, pid, signal.SIGHUP)
                        return 128 + signal.SIGHUP
                    else:
                        forwarded, reports = decoder.feed(data)
                        to_child.extend(forwarded)
                        for report in reports:
                            accepted = geometry.accept(report)
                            if accepted:
                                resize()
                                query_deadline = None
                                query_kind = 6
                            elif report[0] == 6:
                                query_kind = 4
                                query_due = now
                                query_deadline = None
                            else:
                                query_deadline = None
            for ready in writable:
                queue = to_terminal if ready == fd else to_child
                try:
                    length = os.write(ready, queue[:65536])
                except BlockingIOError:
                    continue
                except OSError as error:
                    if ready != master or error.errno != errno.EIO:
                        raise
                    queue.clear()
                    master_open = False
                else:
                    del queue[:length]
    finally:
        signal.set_wakeup_fd(old_wakeup)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        os.close(wake_read)
        os.close(wake_write)


def run(command):
    # Preserve pipelines, scripts and completion generation exactly as Codex does.
    if not interactive(command):
        os.execvp(command[0], command)
    fd = os.open(os.ttyname(0), os.O_RDWR | os.O_NOCTTY | os.O_CLOEXEC)
    attrs = termios.tcgetattr(fd)
    pid = None
    master = None

    def terminate(signum, _frame):
        raise Terminated(signum)

    old_handlers = {
        s: signal.signal(s, terminate)
        for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
    }
    try:
        geometry = Geometry(fd)
        decoder = Input()
        tty.setraw(fd, termios.TCSANOW)
        buffered = initial_probe(fd, geometry, decoder)
        size = geometry.size()
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.close(fd)
                termios.tcsetattr(0, termios.TCSANOW, attrs)
                set_size(0, size)
                os.environ["TCODEX_ACTIVE"] = "1"
                os.execvp(command[0], command)
            except OSError as error:
                print(f"tcodex: {error}", file=sys.stderr)
                os._exit(127 if error.errno == errno.ENOENT else 126)
        return relay(fd, master, pid, attrs, geometry, decoder, buffered)
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        os.close(fd)
        if master is not None:
            os.close(master)
        if pid:
            # Closing the PTY hangs up the child. Reap it even if our relay failed.
            try:
                child, _ = os.waitpid(pid, os.WNOHANG)
                if child == 0:
                    try:
                        os.killpg(pid, signal.SIGHUP)
                    except ProcessLookupError:
                        pass
                    deadline = time.monotonic() + 0.5
                    while not os.waitpid(pid, os.WNOHANG)[0]:
                        if time.monotonic() >= deadline:
                            os.killpg(pid, signal.SIGKILL)
                            os.waitpid(pid, 0)
                            break
                        time.sleep(0.01)
            except ChildProcessError:
                pass


def main():
    try:
        command = ["codex", *sys.argv[1:]]
        if (
            interactive(command)
            and wants_preview_patch(command[1:])
            and os.environ.get("TCODEX_PREVIEW_PATCH") != "0"
        ):
            executable = shutil.which("codex")
            if executable:
                cache = (
                    Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
                    / "tcodex"
                )
                try:
                    command[0] = preview_binary(executable, cache)
                except (OSError, ValueError) as error:
                    print(
                        f"tcodex: larger previews unavailable ({error}); using installed Codex",
                        file=sys.stderr,
                    )
        result = run(command)
    except Terminated as error:
        return 128 + error.signum
    except KeyboardInterrupt:
        return 128 + signal.SIGINT
    except OSError as error:
        print(f"tcodex: {error}", file=sys.stderr)
        return 127 if error.errno == errno.ENOENT else 1
    return result if result >= 0 else 128 - result


if __name__ == "__main__":
    sys.exit(main())
