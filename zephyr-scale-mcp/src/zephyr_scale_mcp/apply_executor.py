from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from zephyr_scale_mcp.apply_log import append_apply_log, latest_apply_entries
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.config import ConfigError, origin_of
from zephyr_scale_mcp.data_policy import sanitize_text
from zephyr_scale_mcp.import_policy import import_labels_for_zephyr
from zephyr_scale_mcp.keys import UnsafeKey
from zephyr_scale_mcp.plan_rules import (
    effective_action,
    fingerprint_from_response,
    operation_hash,
    update_changes,
)

ApplyAction = Literal["create", "update", "delete", "skip"]
_PROTECTED = {"success", "unknown", "started"}


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


def _remember(
    entry: dict[str, Any],
    plan_hash: str | None,
    log_root: Path | None,
    workspace_log_root: Path | None = None,
) -> None:
    if not plan_hash:
        return
    safe = dict(entry)
    if isinstance(safe.get("error"), str):
        safe["error"] = sanitize_text(safe["error"])
    append_apply_log(plan_hash, safe, log_root)
    if workspace_log_root is not None:
        append_apply_log(plan_hash, safe, workspace_log_root)


def _prior_reusable(prior: dict[str, Any] | None, op_hash: str) -> dict[str, Any] | None:
    if not prior:
        return None
    stored = prior.get("op_hash")
    if stored and stored != op_hash and prior.get("status") != "not_run":
        return None
    return prior


def _stop_remaining(
    results: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    start_index: int,
    previous: dict[tuple[str, str], dict[str, Any]],
    *,
    code: str,
    error: str,
    plan_hash: str | None,
    log_root: Path | None,
    workspace_log_root: Path | None,
) -> list[dict[str, Any]]:
    for index in range(start_index, len(operations)):
        operation = operations[index]
        action = effective_action(operation)
        case_id = str(operation.get("case_id") or "")
        op_hash = operation_hash(operation) if isinstance(operation, dict) else ""
        prior = _prior_reusable(previous.get((case_id, action)), op_hash)
        if prior and prior.get("status") == "success":
            results.append(
                {
                    "op_index": index,
                    "case_id": case_id,
                    "action": action,
                    "status": "success",
                    "already_applied": True,
                    "zephyr_key": prior.get("zephyr_key"),
                    "op_hash": op_hash,
                }
            )
            continue
        if prior and prior.get("status") in {"unknown", "started"} and action == "create":
            results.append(
                {
                    "op_index": index,
                    "case_id": case_id,
                    "action": action,
                    "status": "unknown",
                    "code": "RECONCILE_REQUIRED",
                    "op_hash": op_hash,
                    "error": "Исход create неизвестен. Повторно кейс не создаётся, нужна сверка с Zephyr.",
                }
            )
            continue
        pending = {
            "op_index": index,
            "case_id": case_id,
            "action": action,
            "status": "not_run",
            "code": code,
            "op_hash": op_hash,
            "error": error,
        }
        results.append(pending)
        _remember(pending, plan_hash, log_root, workspace_log_root)
    return results


def _local_precheck(client: ZephyrClient, operation: dict[str, Any], action: str) -> None:
    settings = getattr(client, "settings", None)
    if settings is not None and action in {"create", "update", "delete"}:
        settings.auth_header()
        origin_of(settings.base_url)
    if action == "create":
        status = operation.get("status", "Draft")
        priority = operation.get("priority", "Normal")
        if status is None or priority is None or not isinstance(status, str) or not isinstance(priority, str):
            raise UnsafeKey("status и priority должны быть строками.")
    steps = operation.get("steps")
    if steps is not None:
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise UnsafeKey("steps должен быть списком объектов.")


def execute_plan_operations(
    client: ZephyrClient,
    operations: list[dict[str, Any]],
    *,
    plan_hash: str | None = None,
    log_root: Path | None = None,
    workspace_log_root: Path | None = None,
) -> list[dict[str, Any]]:
    previous: dict[tuple[str, str], dict[str, Any]] = {}
    corrupt = False
    if plan_hash:
        previous, corrupt = latest_apply_entries(plan_hash, log_root)
    results: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        action = effective_action(operation)
        case_id = str(operation.get("case_id") or "")
        op_hash = operation_hash(operation)
        entry: dict[str, Any] = {"op_index": index, "case_id": case_id, "action": action, "op_hash": op_hash}
        prior = _prior_reusable(previous.get((case_id, action)), op_hash)
        if prior and prior.get("status") == "success":
            entry["status"] = "success"
            entry["already_applied"] = True
            entry["zephyr_key"] = prior.get("zephyr_key")
            results.append(entry)
            continue
        if prior and prior.get("status") in {"unknown", "started"} and action == "create":
            entry["status"] = "unknown"
            entry["code"] = "RECONCILE_REQUIRED"
            entry["error"] = "Исход create неизвестен. Повторно кейс не создаётся, нужна сверка с Zephyr."
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            continue
        if corrupt and action == "create":
            entry["status"] = "unknown"
            entry["code"] = "RECONCILE_REQUIRED"
            entry["error"] = "Журнал повреждён. Create не повторяется, нужна сверка."
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            continue
        try:
            _local_precheck(client, operation, action)
        except (ConfigError, UnsafeKey, ValueError) as exc:
            entry["status"] = "not_sent"
            entry["code"] = "NOT_SENT"
            entry["error"] = str(exc)
            results.append(entry)
            continue
        try:
            if action == "skip":
                entry["status"] = "skipped"
                entry["result"] = {"ok": True, "skipped": True}
                results.append(entry)
                _remember(entry, plan_hash, log_root, workspace_log_root)
                continue
            if action in {"create", "update", "delete"}:
                _remember(
                    {**entry, "status": "started"},
                    plan_hash,
                    log_root,
                    workspace_log_root,
                )
            if action == "update":
                remote = client.get_test_case(str(operation["test_case_key"]))
                if remote.get("status_code") == 429:
                    entry["status"] = "paused"
                    entry["retry_after"] = remote.get("retry_after")
                    entry["result"] = remote
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    return _stop_remaining(
                        results,
                        operations,
                        index + 1,
                        previous,
                        code="RATE_LIMITED",
                        error="Пачка остановлена: Zephyr ограничил частоту запросов.",
                        plan_hash=plan_hash,
                        log_root=log_root,
                        workspace_log_root=workspace_log_root,
                    )
                remote_status = _op_status(remote)
                if remote_status == "auth":
                    entry["status"] = "failed"
                    entry["code"] = "AUTH_STOPPED"
                    entry["result"] = remote
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    return _stop_remaining(
                        results,
                        operations,
                        index + 1,
                        previous,
                        code="AUTH_STOPPED",
                        error="Пачка остановлена: Zephyr вернул 401 или 403.",
                        plan_hash=plan_hash,
                        log_root=log_root,
                        workspace_log_root=workspace_log_root,
                    )
                if remote_status != "success":
                    entry["status"] = remote_status
                    entry["result"] = remote
                    if remote.get("retry_after") is not None:
                        entry["retry_after"] = remote["retry_after"]
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    continue
                fresh = fingerprint_from_response(remote)
                if fresh != operation.get("baseline_fingerprint"):
                    entry["status"] = "conflict"
                    entry["error"] = "Кейс изменился после чтения для diff. Нужен новый preview."
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    continue
                changes = update_changes(operation, remote)
                if not changes:
                    entry["status"] = "success"
                    entry["code"] = "UNCHANGED"
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    continue
                entry["result"] = client.update_test_case(str(operation["test_case_key"]), **changes)
            elif action == "create":
                entry["result"] = client.create_test_case(
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
            elif action == "delete":
                entry["result"] = client.delete_test_case(str(operation["test_case_key"]))
            else:
                entry["result"] = {
                    "ok": False,
                    "status_code": 400,
                    "error": f"Неизвестное action: {action!r}. Допустимо: create, update, delete.",
                }
        except (ConfigError, UnsafeKey, ValueError) as exc:
            entry["status"] = "not_sent"
            entry["code"] = "NOT_SENT"
            entry["error"] = str(exc)
            results.append(entry)
            continue
        except Exception as exc:  # noqa: BLE001 — исход одного кейса не должен терять уже выполненные
            entry["result"] = {"ok": False, "status_code": 0, "outcome": "unknown", "error": type(exc).__name__}
        result = entry.get("result") or {}
        if result.get("status_code") == 429 or result.get("outcome") == "paused":
            entry["status"] = "paused"
            entry["retry_after"] = result.get("retry_after")
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            return _stop_remaining(
                results,
                operations,
                index + 1,
                previous,
                code="RATE_LIMITED",
                error="Пачка остановлена: Zephyr ограничил частоту запросов.",
                plan_hash=plan_hash,
                log_root=log_root,
                workspace_log_root=workspace_log_root,
            )
        status = _op_status(result)
        if action == "create" and status == "success" and not _zephyr_key(result):
            status = "unknown"
            entry["code"] = "RECONCILE_REQUIRED"
            entry["error"] = "Ответ create не содержит ключ кейса. Нужна сверка, повторный POST не выполняется."
        if status == "auth":
            entry["status"] = "failed"
            entry["code"] = "AUTH_STOPPED"
            entry["error"] = "Zephyr вернул 401 или 403."
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            return _stop_remaining(
                results,
                operations,
                index + 1,
                previous,
                code="AUTH_STOPPED",
                error="Пачка остановлена: Zephyr вернул 401 или 403.",
                plan_hash=plan_hash,
                log_root=log_root,
                workspace_log_root=workspace_log_root,
            )
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
        results.append(entry)
        _remember(entry, plan_hash, log_root, workspace_log_root)
    return results
