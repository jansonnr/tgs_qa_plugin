from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from zephyr_scale_mcp.config import config_dir

_LOG_FIELDS = (
    "op_index",
    "case_id",
    "action",
    "status",
    "code",
    "test_case_key",
    "zephyr_key",
    "error",
    "retry_after",
    "already_applied",
    "op_hash",
)


def apply_log_path(plan_hash: str, root: Path | None = None) -> Path:
    base = root or (config_dir() / "apply-logs")
    return base / f"{plan_hash}.jsonl"


def append_apply_log(plan_hash: str, entry: dict[str, Any], root: Path | None = None) -> Path:
    path = apply_log_path(plan_hash, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: entry[key] for key in _LOG_FIELDS if key in entry and entry[key] is not None}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


class ApplyBusy(RuntimeError):
    """Другой apply этого плана ещё выполняется."""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_alive(pid: int) -> bool:
    import ctypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return kernel.GetLastError() == 5


def _lock_is_stale(path: Path) -> bool:
    try:
        pid = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return False
    return not _pid_alive(pid)


@contextmanager
def hold_apply_lock(plan_hash: str, root: Path | None = None) -> Iterator[None]:
    path = apply_log_path(plan_hash, root).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    for _attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_stale(path):
                try:
                    path.unlink()
                except PermissionError:
                    raise ApplyBusy(plan_hash) from None
                continue
            raise ApplyBusy(plan_hash) from None
        os.write(fd, str(os.getpid()).encode())
        break
    if fd is None:
        raise ApplyBusy(plan_hash)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def latest_apply_entries(plan_hash: str, root: Path | None = None) -> tuple[dict[tuple[str, str], dict[str, Any]], bool]:
    path = apply_log_path(plan_hash, root)
    found: dict[tuple[str, str], dict[str, Any]] = {}
    corrupt = False
    if not path.is_file():
        return found, corrupt
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            corrupt = True
            continue
        if not isinstance(entry, dict):
            corrupt = True
            continue
        case_id = str(entry.get("case_id") or "")
        action = str(entry.get("action") or "")
        if not case_id or not action:
            continue
        previous = found.get((case_id, action))
        if previous and previous.get("status") in {"success", "unknown", "started"} and entry.get("status") == "not_run":
            continue
        found[(case_id, action)] = entry
    return found, corrupt
