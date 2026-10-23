#!/usr/bin/env python3
"""Best-effort Desktop attachment before a browser MCP call; always fail open."""

from __future__ import annotations

import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import socket
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid


TOOL_NAME = "mcp__cua_repl__js"
SOCKET_DIR = Path("/tmp/codex-browser-use")
WAIT_SECONDS = 20.0
PROBE_SECONDS = 0.25
MAX_FRAME = 1024 * 1024


class ConnectionFailure(Exception):
    pass


def find_launcher() -> Path | None:
    # The CLI's `codex` executable is not a Desktop installation.
    for command in ("chatgpt", "codex-desktop"):
        path = shutil.which(command)
        if path:
            return Path(path)
    return None


def executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def owned_socket(path: Path, socket_dir: Path) -> bool:
    if path.parent != socket_dir or path.suffix != ".sock":
        return False
    try:
        info = path.lstat()
        return info.st_uid == os.getuid() and stat.S_ISSOCK(info.st_mode)
    except OSError:
        return False


def recv_exact(client: socket.socket, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Browser handshake timed out")
        client.settimeout(remaining)
        chunk = client.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Browser closed the connection")
        data.extend(chunk)
    return bytes(data)


def probe(path: Path, session_id: str, turn_id: str, timeout: float) -> bool:
    """Use Desktop's read-only, native-endian length-prefixed getInfo RPC."""
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "getInfo",
        "params": {
            "session_id": session_id, "turn_id": turn_id,
            "session_context": "live",
        },
    }).encode()
    deadline = time.monotonic() + timeout
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall(struct.pack("=I", len(request)) + request)
            for _ in range(8):
                size, = struct.unpack("=I", recv_exact(client, 4, deadline))
                if size > MAX_FRAME:
                    return False
                message = json.loads(recv_exact(client, size, deadline))
                if not isinstance(message, dict) or message.get("id") != 1:
                    continue
                result = message.get("result")
                return (
                    "error" not in message
                    and isinstance(result, dict)
                    and result.get("type") == "iab"
                    and isinstance(result.get("metadata"), dict)
                    and result["metadata"].get("codexSessionId") == session_id
                )
    except (OSError, ValueError, TypeError, ConnectionError):
        return False
    return False


def discover(socket_dir: Path, session_id: str, turn_id: str,
             deadline: float, cached: Path | None = None) -> Path | None:
    if cached and owned_socket(cached, socket_dir):
        remaining = deadline - time.monotonic()
        if remaining > 0 and probe(cached, session_id, turn_id,
                                   min(PROBE_SECONDS, remaining)):
            return cached
    try:
        paths = [p for p in socket_dir.glob("*.sock")
                 if p != cached and owned_socket(p, socket_dir)]
        # Prefer recently registered sessions; cap discovery work.
        paths.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
        paths = paths[:64]
    except OSError:
        return None
    remaining = deadline - time.monotonic()
    if not paths or remaining <= 0:
        return None
    timeout = min(PROBE_SECONDS, remaining)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(probe, p, session_id, turn_id, timeout): p
                   for p in paths}
        try:
            for future in concurrent.futures.as_completed(pending, timeout=remaining):
                if future.result():
                    for other in pending:
                        other.cancel()
                    return pending[future]
        except TimeoutError:
            for future in pending:
                future.cancel()
    return None


def save_cache(path: Path, socket_path: Path) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".socket-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(socket_path))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_cache(path: Path) -> Path | None:
    try:
        value = path.read_text().strip()
        return Path(value) if len(value) <= 512 else None
    except OSError:
        return None


def launch_desktop(session_id: str, launcher: Path) -> subprocess.Popen:
    if not executable(launcher):
        raise ConnectionFailure(f"Desktop launcher was not found: {launcher}")
    try:
        return subprocess.Popen(
            [str(launcher), f"codex://threads/{session_id}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as error:
        raise ConnectionFailure(f"Could not start Desktop: {error}") from error


def ensure_connected(session_id: str, turn_id: str, *, socket_dir: Path = SOCKET_DIR,
                     state_dir: Path | None = None, launcher: Path | None = None,
                     wait_seconds: float = WAIT_SECONDS) -> str:
    launcher = launcher if launcher is not None else find_launcher()
    # Non-Desktop hosts, including ordinary CLI/WSL installs, do no work here.
    if launcher is None or not executable(launcher):
        return "unavailable"
    if state_dir is None:
        state_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        state_dir /= "codex-browser-hook"
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = state_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ConnectionFailure("Browser hook cache is not an owned directory")
    deadline = time.monotonic() + wait_seconds
    cache = state_dir / f"{session_id}.socket"
    lock_path = state_dir / f"{session_id}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ConnectionFailure("Timed out waiting for another browser connection attempt")
                time.sleep(0.05)
        connected = discover(socket_dir, session_id, turn_id, deadline, read_cache(cache))
        if connected:
            save_cache(cache, connected)
            return "ready"
        if time.monotonic() >= deadline:
            raise ConnectionFailure("Timed out checking Desktop browser connections")
        process = launch_desktop(session_id, launcher)
        try:
            while time.monotonic() < deadline:
                connected = discover(socket_dir, session_id, turn_id, deadline)
                if connected:
                    save_cache(cache, connected)
                    return "connected"
                result = process.poll()
                if result is not None and result != 0:
                    raise ConnectionFailure(f"Desktop launcher exited with status {result}")
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        finally:
            # An existing Desktop normally acknowledges the deep link and exits.
            # Leave a newly started Desktop running.
            if process.poll() is not None:
                process.wait()
    raise ConnectionFailure(
        f"Desktop did not register this chat within {wait_seconds:g} seconds. "
        "Open this chat in ChatGPT Desktop, then retry the browser call."
    )


def main() -> None:
    try:
        raw = sys.stdin.read(MAX_FRAME + 1)
        if len(raw) > MAX_FRAME:
            raise ConnectionFailure("Hook input is too large")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ConnectionFailure("Expected a hook input object")
        if (event.get("hook_event_name") != "PreToolUse"
                or event.get("tool_name") != TOOL_NAME):
            return
        session_id = event.get("session_id")
        if not isinstance(session_id, str) or str(uuid.UUID(session_id)) != session_id:
            raise ConnectionFailure("Expected a canonical Codex session UUID")
        turn_id = event.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id or len(turn_id) > 128:
            raise ConnectionFailure("Current Codex turn ID is missing or invalid")
        ensure_connected(session_id, turn_id)
    except Exception:
        # Preparation is advisory: retain the original tool's result and policy
        # even if Desktop is missing, its protocol changes, or this helper fails.
        return


if __name__ == "__main__":
    main()
