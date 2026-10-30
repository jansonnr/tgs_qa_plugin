from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Iterator

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

PROTECTED_STATUSES = frozenset({"success", "unknown", "started"})
RECONCILED_ABSENT = "reconciled_absent"


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


def _try_lock(handle: IO[bytes]) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: IO[bytes]) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def hold_apply_lock(plan_hash: str, root: Path | None = None) -> Iterator[None]:
    """Блокировка ОС: снимается при закрытии дескриптора или смерти процесса. Файл не удаляется."""
    path = apply_log_path(plan_hash, root).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if not _try_lock(handle):
            raise ApplyBusy(plan_hash)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()


def latest_apply_entries(
    plan_hash: str, root: Path | None = None
) -> tuple[dict[tuple[str, str], dict[str, Any]], bool]:
    found, corrupt_lines = read_apply_log(plan_hash, root)
    return found, bool(corrupt_lines)


def read_apply_log(
    plan_hash: str, root: Path | None = None
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[int]]:
    """Последняя значимая запись по (case_id, action) и номера повреждённых строк.

    У записи есть служебное поле line — номер строки в журнале.
    """
    path = apply_log_path(plan_hash, root)
    found: dict[tuple[str, str], dict[str, Any]] = {}
    corrupt_lines: list[int] = []
    if not path.is_file():
        return found, corrupt_lines
    raw = path.read_bytes().decode("utf-8", errors="replace")
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            corrupt_lines.append(number)
            continue
        if not isinstance(entry, dict):
            corrupt_lines.append(number)
            continue
        case_id = str(entry.get("case_id") or "")
        action = str(entry.get("action") or "")
        if not case_id or not action:
            continue
        previous = found.get((case_id, action))
        if previous and previous.get("status") in PROTECTED_STATUSES and entry.get("status") == "not_run":
            continue
        entry["line"] = number
        found[(case_id, action)] = entry
    return found, corrupt_lines
