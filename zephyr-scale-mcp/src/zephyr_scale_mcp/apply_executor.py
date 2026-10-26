from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from zephyr_scale_mcp.apply_log import append_apply_log, latest_apply_entries
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.data_policy import sanitize_text
from zephyr_scale_mcp.import_policy import import_labels_for_zephyr
from zephyr_scale_mcp.plan_rules import effective_action, fingerprint_from_response, update_changes

ApplyAction = Literal["create", "update", "delete", "skip"]


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


def _stop_for_auth(
    results: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    start_index: int,
    plan_hash: str | None,
    log_root: Path | None,
    workspace_log_root: Path | None = None,
) -> list[dict[str, Any]]:
    for index in range(start_index, len(operations)):
        operation = operations[index]
        pending = {
            "op_index": index,
            "case_id": operation.get("case_id"),
            "action": effective_action(operation),
            "status": "not_run",
            "code": "AUTH_STOPPED",
            "error": "Пачка остановлена: Zephyr вернул 401 или 403.",
        }
        results.append(pending)
        _remember(pending, plan_hash, log_root, workspace_log_root)
    return results


def execute_plan_operations(
    client: ZephyrClient,
    operations: list[dict[str, Any]],
    *,
    plan_hash: str | None = None,
    log_root: Path | None = None,
    workspace_log_root: Path | None = None,
) -> list[dict[str, Any]]:
    previous = latest_apply_entries(plan_hash, log_root) if plan_hash else {}
    results: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        action = effective_action(operation)
        case_id = str(operation.get("case_id") or "")
        entry: dict[str, Any] = {"op_index": index, "case_id": case_id, "action": action}
        prior = previous.get((case_id, action))
        if prior and prior.get("status") == "success":
            entry["status"] = "success"
            entry["already_applied"] = True
            entry["zephyr_key"] = prior.get("zephyr_key")
            results.append(entry)
            continue
        if prior and prior.get("status") == "unknown" and action == "create":
            entry["status"] = "unknown"
            entry["code"] = "RECONCILE_REQUIRED"
            entry["error"] = "Исход create неизвестен. Повторно кейс не создаётся, нужна сверка с Zephyr."
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            continue
        try:
            if action == "skip":
                entry["status"] = "skipped"
                entry["result"] = {"ok": True, "skipped": True}
                results.append(entry)
                _remember(entry, plan_hash, log_root, workspace_log_root)
                continue
            if action == "update":
                remote = client.get_test_case(str(operation["test_case_key"]))
                remote_status = _op_status(remote)
                if remote_status == "auth":
                    entry["status"] = "failed"
                    entry["code"] = "AUTH_STOPPED"
                    entry["result"] = remote
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    return _stop_for_auth(results, operations, index + 1, plan_hash, log_root, workspace_log_root)
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
                entry["status"] = _op_status(entry["result"])
                zephyr_key = _zephyr_key(entry["result"])
                if zephyr_key:
                    entry["zephyr_key"] = zephyr_key
                if entry["status"] == "auth":
                    entry["status"] = "failed"
                    entry["code"] = "AUTH_STOPPED"
                    entry["error"] = "Zephyr вернул 401 или 403."
                    results.append(entry)
                    _remember(entry, plan_hash, log_root, workspace_log_root)
                    return _stop_for_auth(results, operations, index + 1, plan_hash, log_root, workspace_log_root)
                if entry["status"] != "success":
                    entry["error"] = entry["result"].get("error") or f"Zephyr вернул {entry['result'].get('status_code')}."
                results.append(entry)
                _remember(entry, plan_hash, log_root, workspace_log_root)
                continue
            if action == "create":
                entry["result"] = client.create_test_case(
                    name=str(operation["name"]),
                    objective=operation.get("objective"),
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
        except Exception as exc:  # noqa: BLE001 — исход одного кейса не должен терять уже выполненные
            entry["result"] = {"ok": False, "status_code": 0, "outcome": "unknown", "error": type(exc).__name__}
        result = entry.get("result") or {}
        status = _op_status(result)
        if status == "auth":
            entry["status"] = "failed"
            entry["code"] = "AUTH_STOPPED"
            entry["error"] = "Zephyr вернул 401 или 403."
            results.append(entry)
            _remember(entry, plan_hash, log_root, workspace_log_root)
            return _stop_for_auth(results, operations, index + 1, plan_hash, log_root, workspace_log_root)
        entry["status"] = status
        zephyr_key = _zephyr_key(result)
        if zephyr_key:
            entry["zephyr_key"] = zephyr_key
        if result.get("retry_after") is not None:
            entry["retry_after"] = result["retry_after"]
        if status == "unknown":
            entry["error"] = result.get("error") or "Исход операции неизвестен."
        elif status == "failed":
            entry["error"] = result.get("error") or f"Zephyr вернул {result.get('status_code')}."
        results.append(entry)
        _remember(entry, plan_hash, log_root, workspace_log_root)
    return results
