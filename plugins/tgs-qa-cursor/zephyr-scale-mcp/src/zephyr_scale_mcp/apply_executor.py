from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from zephyr_scale_mcp.apply_log import RECONCILED_ABSENT, append_apply_log, read_apply_log
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.config import ConfigError, origin_of
from zephyr_scale_mcp.data_policy import sanitize_text
from zephyr_scale_mcp.import_policy import import_labels_for_zephyr
from zephyr_scale_mcp.keys import UnsafeKey
from zephyr_scale_mcp.plan_rules import (
    MaskedFieldEdit,
    effective_action,
    fingerprint_from_response,
    operation_hash,
    update_changes,
)

ApplyAction = Literal["create", "update", "delete", "skip"]
_NOT_SENT_ERRORS = (ConfigError, UnsafeKey, MaskedFieldEdit)
_RECONCILE_ERROR = "Исход create неизвестен. Повторно кейс не создаётся: сверь с Zephyr через reconcile_apply."


class _JournalUnavailable(Exception):
    """Основной журнал не записался: продолжать пачку нельзя."""


class _BatchStop(Exception):
    def __init__(self, code: str, error: str) -> None:
        super().__init__(error)
        self.code = code
        self.error = error


def _op_status(result: dict[str, Any]) -> str:
    if result.get("outcome") == "unknown":
        return "unknown"
    if result.get("ok") is True:
        return "success"
    status_code = result.get("status_code")
    if status_code in (0, None):
        return "unknown"
    if status_code in (401, 403):
        return "auth"
    if isinstance(status_code, int) and status_code >= 500:
        return "unknown"
    return "failed"


def _zephyr_key(result: dict[str, Any]) -> str | None:
    data = result.get("data")
    if isinstance(data, dict):
        key = data.get("key") or data.get("testCaseKey")
        if key:
            return str(key)
    return None


def _precondition(operation: dict[str, Any]) -> str | None:
    if isinstance(operation.get("precondition"), str):
        return operation["precondition"]
    lines = operation.get("preconditions")
    if isinstance(lines, list) and lines:
        return "\n".join(str(line) for line in lines)
    return None


class _Journal:
    def __init__(self, plan_hash: str | None, log_root: Path | None, workspace_log_root: Path | None) -> None:
        self.plan_hash = plan_hash
        self.log_root = log_root
        self.workspace_log_root = workspace_log_root

    def remember(self, entry: dict[str, Any]) -> None:
        if not self.plan_hash:
            return
        safe = dict(entry)
        if isinstance(safe.get("error"), str):
            safe["error"] = sanitize_text(safe["error"])
        try:
            append_apply_log(self.plan_hash, safe, self.log_root)
        except OSError as exc:
            raise _JournalUnavailable(type(exc).__name__) from exc
        if self.workspace_log_root is not None:
            try:
                append_apply_log(self.plan_hash, safe, self.workspace_log_root)
            except OSError as exc:
                entry["workspace_log_error"] = type(exc).__name__

    def remember_quietly(self, entry: dict[str, Any]) -> None:
        try:
            self.remember(entry)
        except _JournalUnavailable:
            entry["log_error"] = "Журнал недоступен, запись не сохранена."


def _history_decision(
    prior: dict[str, Any] | None,
    *,
    action: str,
    op_hash: str,
    corrupt_lines: list[int],
) -> dict[str, Any] | None:
    """Результат по истории без обращения к Zephyr или None, если операцию можно отправлять."""
    status = prior.get("status") if prior else None
    stored_hash = prior.get("op_hash") if prior else None
    if status == "success":
        if not stored_hash or stored_hash == op_hash:
            return {"status": "success", "already_applied": True, "zephyr_key": prior.get("zephyr_key")}
        if action == "create":
            return {
                "status": "conflict",
                "code": "ALREADY_CREATED",
                "zephyr_key": prior.get("zephyr_key"),
                "error": "Кейс уже создан по прежней версии строки. Повторный create не выполняется: "
                "переведи строку в update этого ключа.",
            }
        return None
    if action != "create":
        return None
    if status in {"unknown", "started"}:
        return {"status": "unknown", "code": "RECONCILE_REQUIRED", "error": _RECONCILE_ERROR}
    if corrupt_lines and (prior is None or int(prior.get("line") or 0) < max(corrupt_lines)):
        lines = ", ".join(str(number) for number in corrupt_lines[:10])
        return {
            "status": "unknown",
            "code": "RECONCILE_REQUIRED",
            "error": f"Журнал повреждён (строки {lines}). Create не повторяется: сверь с Zephyr через reconcile_apply.",
        }
    return None


def _local_precheck(client: ZephyrClient, operation: dict[str, Any], action: str) -> None:
    settings = getattr(client, "settings", None)
    if settings is not None and action in {"create", "update", "delete"}:
        settings.auth_header()
        origin_of(settings.base_url)
    if action == "create":
        for field in ("status", "priority"):
            value = operation.get(field, "Draft" if field == "status" else "Normal")
            if not isinstance(value, str) or not value.strip():
                raise UnsafeKey("status и priority должны быть непустыми строками.")
    steps = operation.get("steps")
    if steps is not None:
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise UnsafeKey("steps должен быть списком объектов.")


def _read_for_write(client: ZephyrClient, operation: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    """Свежий GET перед update/delete. None — запись делать нельзя, entry уже заполнен."""
    remote = client.get_test_case(str(operation["test_case_key"]))
    if remote.get("status_code") == 429 or remote.get("outcome") == "paused":
        entry["status"] = "paused"
        entry["retry_after"] = remote.get("retry_after")
        raise _BatchStop("RATE_LIMITED", "Пачка остановлена: Zephyr ограничил частоту запросов.")
    remote_status = _op_status(remote)
    if remote_status == "auth":
        entry["status"] = "failed"
        entry["code"] = "AUTH_STOPPED"
        entry["error"] = "Zephyr вернул 401 или 403."
        raise _BatchStop("AUTH_STOPPED", "Пачка остановлена: Zephyr вернул 401 или 403.")
    if remote_status != "success":
        entry["status"] = remote_status
        entry["error"] = remote.get("error") or f"Чтение кейса перед записью: Zephyr вернул {remote.get('status_code')}."
        return None
    if fingerprint_from_response(remote) != operation.get("baseline_fingerprint"):
        entry["status"] = "conflict"
        entry["error"] = "Кейс изменился после чтения для diff. Нужен новый preview."
        return None
    return remote


def _send(client: ZephyrClient, operation: dict[str, Any], action: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    if action == "update":
        remote = _read_for_write(client, operation, entry)
        if remote is None:
            return None
        changes = update_changes(operation, remote)
        if not changes:
            entry["status"] = "success"
            entry["code"] = "UNCHANGED"
            return None
        return client.update_test_case(str(operation["test_case_key"]), **changes)
    if action == "delete":
        if _read_for_write(client, operation, entry) is None:
            return None
        return client.delete_test_case(str(operation["test_case_key"]))
    return client.create_test_case(
        name=str(operation["name"]),
        objective=operation.get("objective"),
        precondition=_precondition(operation),
        folder=operation.get("folder"),
        status=str(operation.get("status", "Draft")),
        priority=str(operation.get("priority", "Normal")),
        project_key=operation.get("project_key"),
        steps=operation.get("steps"),
        labels=import_labels_for_zephyr(),
    )


def _finish(entry: dict[str, Any], action: str, result: dict[str, Any]) -> None:
    if result.get("status_code") == 429 or result.get("outcome") == "paused":
        entry["status"] = "paused"
        entry["retry_after"] = result.get("retry_after")
        raise _BatchStop("RATE_LIMITED", "Пачка остановлена: Zephyr ограничил частоту запросов.")
    status = _op_status(result)
    if status == "auth":
        entry["status"] = "failed"
        entry["code"] = "AUTH_STOPPED"
        entry["error"] = "Zephyr вернул 401 или 403."
        raise _BatchStop("AUTH_STOPPED", "Пачка остановлена: Zephyr вернул 401 или 403.")
    if action == "create" and status == "success" and not _zephyr_key(result):
        status = "unknown"
        entry["code"] = "RECONCILE_REQUIRED"
        entry["error"] = "Ответ create не содержит ключ кейса. Нужна сверка, повторный POST не выполняется."
    entry["status"] = status
    zephyr_key = _zephyr_key(result)
    if zephyr_key:
        entry["zephyr_key"] = zephyr_key
    if result.get("retry_after") is not None:
        entry["retry_after"] = result["retry_after"]
    if status == "unknown" and "error" not in entry:
        entry["error"] = result.get("error") or "Исход операции неизвестен."
    elif status == "failed":
        entry["error"] = result.get("error") or f"Zephyr вернул {result.get('status_code')}."


def _stop_remaining(
    results: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    start_index: int,
    previous: dict[tuple[str, str], dict[str, Any]],
    corrupt_lines: list[int],
    journal: _Journal,
    *,
    code: str,
    error: str,
) -> list[dict[str, Any]]:
    for index in range(start_index, len(operations)):
        operation = operations[index]
        action = effective_action(operation)
        case_id = str(operation.get("case_id") or "")
        op_hash = operation_hash(operation)
        entry: dict[str, Any] = {"op_index": index, "case_id": case_id, "action": action, "op_hash": op_hash}
        decided = _history_decision(
            previous.get((case_id, action)), action=action, op_hash=op_hash, corrupt_lines=corrupt_lines
        )
        if decided is not None:
            entry.update(decided)
            results.append(entry)
            continue
        entry.update({"status": "not_run", "code": code, "error": error})
        results.append(entry)
        journal.remember_quietly(entry)
    return results


def execute_plan_operations(
    client: ZephyrClient,
    operations: list[dict[str, Any]],
    *,
    plan_hash: str | None = None,
    log_root: Path | None = None,
    workspace_log_root: Path | None = None,
) -> list[dict[str, Any]]:
    previous: dict[tuple[str, str], dict[str, Any]] = {}
    corrupt_lines: list[int] = []
    if plan_hash:
        previous, corrupt_lines = read_apply_log(plan_hash, log_root)
    journal = _Journal(plan_hash, log_root, workspace_log_root)
    results: list[dict[str, Any]] = []

    def stop(index: int, code: str, error: str) -> list[dict[str, Any]]:
        return _stop_remaining(
            results, operations, index + 1, previous, corrupt_lines, journal, code=code, error=error
        )

    for index, operation in enumerate(operations):
        action = effective_action(operation)
        case_id = str(operation.get("case_id") or "")
        op_hash = operation_hash(operation)
        entry: dict[str, Any] = {"op_index": index, "case_id": case_id, "action": action, "op_hash": op_hash}
        if operation.get("test_case_key"):
            entry["test_case_key"] = str(operation["test_case_key"])
        decided = _history_decision(
            previous.get((case_id, action)), action=action, op_hash=op_hash, corrupt_lines=corrupt_lines
        )
        if decided is not None:
            entry.update(decided)
            results.append(entry)
            continue
        if action == "skip":
            entry["status"] = "skipped"
            results.append(entry)
            journal.remember_quietly(entry)
            continue
        if action not in {"create", "update", "delete"}:
            entry["status"] = "failed"
            entry["error"] = f"Неизвестное action: {action!r}. Допустимо: create, update, delete, skip."
            results.append(entry)
            journal.remember_quietly(entry)
            continue
        try:
            _local_precheck(client, operation, action)
        except (*_NOT_SENT_ERRORS, ValueError) as exc:
            entry.update({"status": "not_sent", "code": "NOT_SENT", "error": str(exc)})
            results.append(entry)
            journal.remember_quietly(entry)
            continue
        try:
            journal.remember({**entry, "status": "started"})
        except _JournalUnavailable:
            entry.update(
                {
                    "status": "not_sent",
                    "code": "LOG_UNAVAILABLE",
                    "error": "Журнал apply не записывается. Запрос в Zephyr не отправлен.",
                }
            )
            results.append(entry)
            return stop(index, "LOG_UNAVAILABLE", "Пачка остановлена: журнал apply недоступен.")
        try:
            result = _send(client, operation, action, entry)
            if result is not None:
                _finish(entry, action, result)
        except _BatchStop as halt:
            results.append(entry)
            journal.remember_quietly(entry)
            return stop(index, halt.code, halt.error)
        except _NOT_SENT_ERRORS as exc:
            entry.update({"status": "not_sent", "code": "NOT_SENT", "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — исход одного кейса не должен терять уже выполненные
            entry.update({"status": "unknown", "error": type(exc).__name__})
        results.append(entry)
        try:
            journal.remember(entry)
        except _JournalUnavailable:
            entry["log_error"] = "Результат не записан в журнал. При повторе create потребует сверки."
            return stop(index, "LOG_UNAVAILABLE", "Пачка остановлена: журнал apply недоступен.")
    return results


def reconcile_entry(
    *,
    case_id: str,
    action: str,
    op_hash: str,
    resolution: str,
    zephyr_key: str | None,
) -> dict[str, Any]:
    """Запись сверки unknown/started create: найден в Zephyr (success) или подтверждено отсутствие."""
    entry: dict[str, Any] = {"case_id": case_id, "action": action, "op_hash": op_hash, "code": "RECONCILED"}
    if resolution == "created":
        entry["status"] = "success"
        entry["zephyr_key"] = zephyr_key
    else:
        entry["status"] = RECONCILED_ABSENT
    return entry
