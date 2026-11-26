"""Lifecycle management for Electronic Team Serial Port Monitor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

_APP_NAME = "Serial Port Monitor"


def _workspace() -> Path:
    return Path(os.environ.get("SERIAL_SPM_WORKSPACE", os.getcwd())).expanduser().resolve()


def _state_file() -> Path:
    return _workspace() / ".serial-spm-mcp" / "state.json"


def _read_state() -> dict[str, Any]:
    path = _state_file()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value.setdefault("monitors", {})
            value.setdefault("captures", [])
            return value
        return {"monitors": {}, "captures": []}
    except FileNotFoundError:
        return {"monitors": {}, "captures": []}
    except (json.JSONDecodeError, OSError):
        return {"monitors": {}, "captures": []}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def _monitor_executable() -> Path:
    configured = os.environ.get("SERIAL_SPM_MONITOR_EXE")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Electronic Team"
            / _APP_NAME
            / "SerialMonitorx64.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Electronic Team, Inc"
            / _APP_NAME
            / "SerialMonitorx64.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Electronic Team"
            / _APP_NAME
            / "SerialMonitor.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Electronic Team, Inc"
            / _APP_NAME
            / "SerialMonitor.exe",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Serial Port Monitor was not found. Set SERIAL_SPM_MONITOR_EXE to its executable path."
    )


def _is_our_monitor(entry: dict[str, Any]) -> bool:
    try:
        if entry.get("running") is False:
            return False
        process = psutil.Process(int(entry["pid"]))
        if not process.is_running():
            return False
        expected = Path(str(entry["executable"])).name.casefold()
        actual = Path(process.name()).name.casefold()
        if actual != expected:
            return False
        return abs(process.create_time() - float(entry["created_at"])) < 2.0
    except (KeyError, ValueError, psutil.Error, OSError):
        return False


def start_monitor(port: str) -> dict[str, Any]:
    """Start or reuse a Terminal-view monitor, logging inside the workspace."""
    if sys.platform != "win32":
        raise OSError("Serial Port Monitor is available only on Windows.")
    if "://" in port:
        raise ValueError("SPM can monitor local COM ports only; network serial URLs are not supported.")

    executable = _monitor_executable()
    state = _read_state()
    monitors = state.setdefault("monitors", {})
    previous = monitors.get(port)
    if isinstance(previous, dict) and _is_our_monitor(previous):
        return {"port": port, "running": True, "reused": True, "log_path": previous["log_path"], "pid": previous["pid"]}

    log_dir = _workspace() / "logs" / "spm"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S-%f")
    safe_port = "".join(character if character.isalnum() or character in "._-" else "_" for character in port)
    log_path = log_dir / f"{safe_port}-{stamp}.log"
    args = [str(executable), "/new", port, f"R:U={log_path}"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
    )
    process = subprocess.Popen(
        args,
        cwd=str(_workspace()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    try:
        created_at = psutil.Process(process.pid).create_time()
    except psutil.Error:
        created_at = datetime.now().timestamp()
    entry = {
        "port": port,
        "pid": process.pid,
        "created_at": created_at,
        "executable": str(executable),
        "log_path": str(log_path),
        "started_at": datetime.now().astimezone().isoformat(),
    }
    monitors[port] = entry
    state.setdefault("captures", []).append({"port": port, "log_path": str(log_path), "started_at": entry["started_at"]})
    _write_state(state)
    return {**entry, "running": True, "reused": False, "view": "terminal"}


def list_monitors() -> dict[str, Any]:
    state = _read_state()
    monitors = state.setdefault("monitors", {})
    active: list[dict[str, Any]] = []
    for port, entry in list(monitors.items()):
        if not isinstance(entry, dict) or not _is_our_monitor(entry):
            monitors.pop(port, None)
            continue
        active.append({"port": port, "pid": entry["pid"], "log_path": entry["log_path"], "started_at": entry["started_at"]})
    _write_state(state)
    return {"workspace": str(_workspace()), "monitors": active}


def close_monitor(port: str | None = None) -> dict[str, Any]:
    """Close only process IDs recorded by this server; preserve all capture files."""
    state = _read_state()
    monitors = state.setdefault("monitors", {})
    selected = [port] if port is not None else list(monitors)
    closed: list[str] = []
    already_stopped: list[str] = []
    for item in selected:
        entry = monitors.get(item)
        if not isinstance(entry, dict):
            already_stopped.append(item)
            continue
        if _is_our_monitor(entry):
            try:
                psutil.Process(int(entry["pid"])).terminate()
                closed.append(item)
            except psutil.Error:
                already_stopped.append(item)
        else:
            already_stopped.append(item)
        entry["running"] = False
    _write_state(state)
    return {"closed": closed, "already_stopped": already_stopped, "logs_preserved": True}


def read_log(port: str | None = None, tail_lines: int = 100, pattern: str | None = None) -> dict[str, Any]:
    """Read a bounded tail from a monitor log without accepting arbitrary paths."""
    if tail_lines < 1 or tail_lines > 5000:
        raise ValueError("tail_lines must be between 1 and 5000.")
    state = _read_state()
    captures = state.get("captures", [])
    if port is None:
        entries = list(captures)
        if not entries:
            raise FileNotFoundError("No SPM capture logs are registered.")
        entry = max(entries, key=lambda item: item.get("started_at", ""))
    else:
        entries = [item for item in captures if item.get("port") == port]
        if not entries:
            raise FileNotFoundError(f"No SPM capture log is registered for {port}.")
        entry = max(entries, key=lambda item: item.get("started_at", ""))
    path = Path(entry["log_path"]).resolve()
    if not path.is_relative_to((_workspace() / "logs" / "spm").resolve()):
        raise ValueError("The registered log path is outside the workspace capture directory.")
    try:
        text = path.read_text(encoding="utf-16")
    except UnicodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if pattern:
        import re

        compiled = re.compile(pattern, re.IGNORECASE)
        lines = [line for line in lines if compiled.search(line)]
    return {"port": entry["port"], "log_path": str(path), "line_count": len(lines), "text": "\n".join(lines[-tail_lines:])}
