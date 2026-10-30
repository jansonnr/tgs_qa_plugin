"""Доработки по ревью 0.3.5: история операций, сверка, скрытые поля, контракт плана."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from typing import Any

import pytest

import zephyr_scale_mcp.apply_log as apply_log
import zephyr_scale_mcp.config as config
import zephyr_scale_mcp.server as server
from zephyr_scale_mcp.apply_executor import execute_plan_operations
from zephyr_scale_mcp.apply_log import (
    ApplyBusy,
    append_apply_log,
    apply_log_path,
    hold_apply_lock,
    read_apply_log,
)
from zephyr_scale_mcp.config import Settings
from zephyr_scale_mcp.data_policy import MAX_AGENT_STRING, agent_view
from zephyr_scale_mcp.plan_rules import (
    MaskedFieldEdit,
    PlanRejected,
    adapt_plan,
    extract_search_page,
    fingerprint_from_response,
    operation_hash,
    update_changes,
    validate_plan,
)

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


class FakeZephyr:
    def __init__(self, remote: dict[str, Any] | None = None) -> None:
        self.settings = Settings(bearer_token="synthetic", base_url="https://zephyr.invalid/soft")
        self.remote = remote or {}
        self.creates: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.deletes: list[str] = []
        self.create_result: dict[str, Any] = {"ok": True, "status_code": 201, "data": {"key": "QA-T10"}}

    def create_test_case(self, **kwargs: Any) -> dict[str, Any]:
        self.creates.append(kwargs)
        return self.create_result

    def get_test_case(self, key: str) -> dict[str, Any]:
        if key not in self.remote:
            return {"ok": False, "status_code": 404, "data": None}
        return {"ok": True, "status_code": 200, "data": self.remote[key]}

    def update_test_case(self, key: str, **changes: Any) -> dict[str, Any]:
        self.updates.append({"key": key, **changes})
        return {"ok": True, "status_code": 200, "data": {"key": key}}

    def delete_test_case(self, key: str) -> dict[str, Any]:
        self.deletes.append(key)
        return {"ok": True, "status_code": 204, "data": None}


def _run(client: FakeZephyr, operations: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    return execute_plan_operations(client, operations, plan_hash="run", log_root=root)  # type: ignore[arg-type]


# --- C04 / C21: изменённая строка не создаёт кейс второй раз


def test_changed_row_after_success_is_not_created_again(tmp_path: Path) -> None:
    client = FakeZephyr()
    _run(client, [{"case_id": "one", "action": "create", "name": "One"}], tmp_path)
    second = _run(client, [{"case_id": "one", "action": "create", "name": "One renamed"}], tmp_path)
    assert len(client.creates) == 1
    assert second[0]["status"] == "conflict"
    assert second[0]["code"] == "ALREADY_CREATED"
    assert second[0]["zephyr_key"] == "QA-T10"
    third = _run(client, [{"case_id": "one", "action": "create", "name": "One renamed"}], tmp_path)
    assert third[0]["code"] == "ALREADY_CREATED"
    assert len(client.creates) == 1


def test_changed_row_after_unknown_requires_reconcile(tmp_path: Path) -> None:
    client = FakeZephyr()
    client.create_result = {"ok": False, "status_code": 0, "outcome": "unknown", "error": "ReadTimeout"}
    _run(client, [{"case_id": "two", "action": "create", "name": "Two"}], tmp_path)
    client.create_result = {"ok": True, "status_code": 201, "data": {"key": "QA-T11"}}
    second = _run(client, [{"case_id": "two", "action": "create", "name": "Two corrected"}], tmp_path)
    assert second[0]["code"] == "RECONCILE_REQUIRED"
    assert len(client.creates) == 1


# --- C03: журнал и границы HTTP


def test_journal_failure_before_http_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeZephyr()

    def broken(*_args: Any, **_kwargs: Any) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr("zephyr_scale_mcp.apply_executor.append_apply_log", broken)
    results = _run(
        client,
        [
            {"case_id": "a", "action": "create", "name": "A"},
            {"case_id": "b", "action": "create", "name": "B"},
        ],
        tmp_path,
    )
    assert client.creates == []
    assert results[0]["code"] == "LOG_UNAVAILABLE"
    assert results[1]["status"] == "not_run"


def test_journal_failure_after_http_blocks_blind_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeZephyr()
    real = apply_log.append_apply_log
    calls = {"n": 0}

    def flaky(plan_hash: str, entry: dict[str, Any], root: Path | None = None) -> Path:
        calls["n"] += 1
        if entry.get("status") != "started":
            raise OSError("disk full")
        return real(plan_hash, entry, root)

    monkeypatch.setattr("zephyr_scale_mcp.apply_executor.append_apply_log", flaky)
    first = _run(client, [{"case_id": "a", "action": "create", "name": "A"}], tmp_path)
    assert first[0]["status"] == "success"
    assert "log_error" in first[0]
    monkeypatch.setattr("zephyr_scale_mcp.apply_executor.append_apply_log", real)
    second = _run(client, [{"case_id": "a", "action": "create", "name": "A"}], tmp_path)
    assert second[0]["code"] == "RECONCILE_REQUIRED"
    assert len(client.creates) == 1


def test_workspace_log_failure_does_not_lose_result(tmp_path: Path) -> None:
    client = FakeZephyr()
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x", encoding="utf-8")
    results = execute_plan_operations(
        client,  # type: ignore[arg-type]
        [{"case_id": "a", "action": "create", "name": "A"}],
        plan_hash="run",
        log_root=tmp_path / "main",
        workspace_log_root=blocked,
    )
    assert results[0]["status"] == "success"
    assert "workspace_log_error" in results[0]
    found, _ = read_apply_log("run", tmp_path / "main")
    assert found[("a", "create")]["status"] == "success"


# --- C23: заведомо неотправленный запрос не блокирует повтор


def test_not_sent_after_started_allows_retry(tmp_path: Path) -> None:
    secret = "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    remote = {"name": "Case", "objective": f"Токен {secret}", "testScript": {"steps": []}}
    client = FakeZephyr({"QA-T1": remote})
    operation = {
        "case_id": "u",
        "action": "update",
        "test_case_key": "QA-T1",
        "baseline_fingerprint": fingerprint_from_response({"data": remote}),
        "objective": "Новый текст и [secret]",
    }
    first = _run(client, [operation], tmp_path)
    assert first[0]["status"] == "not_sent"
    assert client.updates == []
    found, _ = read_apply_log("run", tmp_path)
    assert found[("u", "update")]["status"] == "not_sent"


# --- C24: повреждённый журнал и сверка


def test_corrupt_log_blocks_create_until_reconciled(tmp_path: Path) -> None:
    client = FakeZephyr()
    path = apply_log_path("run", tmp_path)
    path.write_text('{"case_id":"a","act\n', encoding="utf-8")
    operation = {"case_id": "a", "action": "create", "name": "A"}
    blocked = _run(client, [operation], tmp_path)
    assert blocked[0]["code"] == "RECONCILE_REQUIRED"
    assert "строки 1" in blocked[0]["error"]
    append_apply_log(
        "run",
        {"case_id": "a", "action": "create", "status": "reconciled_absent", "op_hash": operation_hash(operation)},
        tmp_path,
    )
    created = _run(client, [operation], tmp_path)
    assert created[0]["status"] == "success"
    again = _run(client, [operation], tmp_path)
    assert again[0]["already_applied"] is True
    assert len(client.creates) == 1


def test_entry_after_corruption_is_trusted(tmp_path: Path) -> None:
    path = apply_log_path("run", tmp_path)
    path.write_text(
        '{"case_id":"x","act\n{"case_id":"a","action":"create","status":"failed","op_hash":"h"}\n',
        encoding="utf-8",
    )
    found, corrupt = read_apply_log("run", tmp_path)
    assert corrupt == [1]
    assert found[("a", "create")]["line"] == 2


# --- C08: блокировка ОС


def _hold_and_die(path: str, ready: Any) -> None:
    import os

    from zephyr_scale_mcp.apply_log import hold_apply_lock as lock

    with lock("crash-hash", Path(path)):
        ready.set()
        os._exit(1)


def test_lock_is_released_when_owner_dies(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    proc = ctx.Process(target=_hold_and_die, args=(str(tmp_path), ready))
    proc.start()
    assert ready.wait(10)
    proc.join(10)
    assert proc.exitcode == 1
    with hold_apply_lock("crash-hash", tmp_path):
        pass


def test_leftover_lock_file_does_not_block(tmp_path: Path) -> None:
    apply_log_path("left", tmp_path).with_suffix(".lock").write_text("", encoding="utf-8")
    with hold_apply_lock("left", tmp_path):
        with pytest.raises(ApplyBusy):
            with hold_apply_lock("left", tmp_path):
                pass


# --- C13: скрытые поля в update


def test_truncated_step_is_restored_from_zephyr() -> None:
    long_text = "x" * (MAX_AGENT_STRING + 50)
    remote = {
        "ok": True,
        "data": {
            "name": "Case",
            "testScript": {
                "steps": [
                    {"id": 1, "description": long_text, "expectedResult": "ok"},
                    {"id": 2, "description": "Второй", "expectedResult": "ok"},
                ]
            },
        },
    }
    changes = update_changes(
        {
            "steps": [
                {"description": agent_view(long_text), "expectedResult": "ok"},
                {"description": "Второй изменён", "expectedResult": "ok"},
            ]
        },
        remote,
    )
    steps = changes["steps"]
    assert steps[0]["description"] == long_text
    assert steps[0]["id"] == 1
    assert steps[1]["description"] == "Второй изменён"


def test_edit_of_masked_field_with_placeholder_is_rejected() -> None:
    remote = {"ok": True, "data": {"name": "Case", "precondition": "Bearer abcdefghijklmnopqrstuvwxyz0123456789"}}
    with pytest.raises(MaskedFieldEdit):
        update_changes({"precondition": "Логин и [secret]"}, remote)


# --- C25 / C10: схема операции до preview


@pytest.mark.parametrize(
    "operation",
    [
        {"case_id": "c", "action": "create", "name": "A", "steps": [{"expectedResult": "ok"}]},
        {"case_id": "c", "action": "create", "name": "A", "steps": [{"description": "Open", "testData": 5}]},
        {"case_id": "c", "action": "create", "name": "A", "steps": [{"description": "Open", "data": "x"}]},
        {"case_id": "c", "action": "create", "name": "A", "status": None},
        {"case_id": "c", "action": "create", "name": "A", "priority": ""},
        {"case_id": "c", "action": "create", "name": "A", "labels": ["smoke"]},
        {"case_id": "c", "action": "create", "name": "A", "project_key": "../QA"},
        {"case_id": "c", "action": "delete", "test_case_key": "QA-T1"},
    ],
)
def test_invalid_operation_is_rejected_before_preview(operation: dict[str, Any]) -> None:
    with pytest.raises(PlanRejected) as caught:
        validate_plan({"search_status": "ok", "operations": [operation]})
    assert caught.value.code == "PLAN_INVALID"


def test_delete_checks_fresh_baseline(tmp_path: Path) -> None:
    remote = {"name": "Old", "testScript": {"steps": []}}
    client = FakeZephyr({"QA-T5": remote})
    baseline = fingerprint_from_response({"data": remote})
    remote["name"] = "Changed by someone"
    results = _run(
        client,
        [{"case_id": "d", "action": "delete", "test_case_key": "QA-T5", "baseline_fingerprint": baseline}],
        tmp_path,
    )
    assert results[0]["status"] == "conflict"
    assert client.deletes == []


# --- C01: опубликованные примеры проходят через адаптер


def test_published_examples_pass_through_adapter() -> None:
    plan = json.loads((SCHEMAS / "dedupe-plan.example.json").read_text(encoding="utf-8"))
    draft = json.loads((SCHEMAS / "draft-testcases.example.json").read_text(encoding="utf-8"))
    with pytest.raises(PlanRejected) as caught:
        validate_plan(adapt_plan(plan, draft))
    assert caught.value.code == "ASK_UNRESOLVED"
    plan["items"][0]["resolved_action"] = "skip"
    adapted = adapt_plan(plan, draft)
    validate_plan(adapted)
    create = adapted["operations"][1]
    assert create["case_id"] == "2"
    assert create["folder"] == "/QA/Payments"
    assert create["precondition"] == "Пользователь авторизован"
    assert create["steps"][1] == {
        "description": "Ввести данные карты с отказом банка",
        "testData": "4000000000000002 / 12/30 / 123",
        "expectedResult": "Ошибок валидации нет",
    }
    assert "testData" not in create["steps"][0]


def test_draft_revision_mismatch_is_rejected() -> None:
    plan = {"run_id": "r", "draft_revision": 3, "search_status": "ok", "items": []}
    with pytest.raises(PlanRejected) as caught:
        adapt_plan(plan, {"run_id": "r", "revision": 2, "cases": []})
    assert caught.value.code == "DRAFT_MISMATCH"


def test_draft_columns_of_different_length_are_rejected() -> None:
    plan = {"run_id": "r", "search_status": "ok", "items": [{"draft_id": "1", "action": "create"}]}
    draft = {"run_id": "r", "cases": [{"draft_id": "1", "name": "A", "steps": ["a", "b"], "expected_results": ["x"]}]}
    with pytest.raises(PlanRejected):
        adapt_plan(plan, draft)


def test_matcher_accepts_raw_draft_case_and_sees_data_difference() -> None:
    from zephyr_scale_mcp.plan_rules import match_candidates

    draft = json.loads((SCHEMAS / "draft-testcases.example.json").read_text(encoding="utf-8"))
    case = dict(draft["cases"][1], confirmed_skip=True)
    same_steps = adapt_plan(
        {"run_id": draft["run_id"], "search_status": "ok", "items": [{"draft_id": "2", "action": "create"}]}, draft
    )["operations"][0]["steps"]
    other_data = [dict(step) for step in same_steps]
    other_data[1]["testData"] = "4111111111111111 / 12/30 / 123"
    index = [
        {"key": "QA-T1", "name": case["name"], "precondition": "Пользователь авторизован", "steps": same_steps},
        {"key": "QA-T2", "name": case["name"], "precondition": "Пользователь авторизован", "steps": other_data},
    ]
    exact = match_candidates(index[:1], [case])["results"][0]
    assert exact["case_id"] == "2"
    assert exact["suggested_action"] == "skip"
    differs = match_candidates(index[1:], [case])["results"][0]
    assert differs["suggested_action"] == "ask"
    assert "шаг 2" in differs["note"]


# --- C06: строки без ключа — неизвестная схема


def test_rows_without_key_are_unknown_schema() -> None:
    rows, _total = extract_search_page({"ok": True, "data": [{"name": "no key"}]})
    assert rows is None


# --- Сквозной сценарий через tools MCP (C05, C18, C24 — reconcile)


@pytest.fixture()
def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeZephyr:
    settings = Settings(bearer_token="synthetic", base_url="https://zephyr.invalid/soft", project_key="QA", project_id="101")
    monkeypatch.setattr(config, "_runtime", settings)
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(apply_log, "config_dir", lambda: tmp_path)
    fake = FakeZephyr()
    fake.settings = settings
    monkeypatch.setattr(server, "_zephyr_client", fake)
    return fake


def _plan(*operations: dict[str, Any], run_id: str = "20261029-qa") -> dict[str, Any]:
    return {"run_id": run_id, "search_status": "ok", "operations": list(operations)}


def test_plan_without_run_id_is_rejected(mcp_env: FakeZephyr) -> None:
    payload = json.loads(server.prepare_apply({"search_status": "ok", "operations": [{"case_id": "a", "action": "create", "name": "A"}]}))
    assert payload["code"] == "PLAN_INVALID"


def test_mixed_projects_are_rejected(mcp_env: FakeZephyr) -> None:
    plan = _plan(
        {"case_id": "a", "action": "create", "name": "A", "project_key": "QA"},
        {"case_id": "b", "action": "create", "name": "B", "project_key": "OTHER"},
    )
    assert json.loads(server.prepare_apply(plan))["code"] == "TARGET_MIXED"
    foreign = _plan({"case_id": "u", "action": "update", "test_case_key": "OTHER-T1", "baseline_fingerprint": "x", "name": "N"})
    assert json.loads(server.prepare_apply(foreign))["code"] == "TARGET_MIXED"


def test_preview_shows_resolved_target_and_create_project(mcp_env: FakeZephyr) -> None:
    prepared = json.loads(server.prepare_apply(_plan({"case_id": "a", "action": "create", "name": "A"})))
    assert prepared["target"] == {"origin": "https://zephyr.invalid", "project_key": "QA"}
    assert prepared["operations"][0]["project_key"] == "QA"
    applied = json.loads(server.apply_plan(prepared["apply_token"], _plan({"case_id": "a", "action": "create", "name": "A"})))
    assert applied["ok"] is True
    assert mcp_env.creates[0]["project_key"] == "QA"


def test_settings_change_between_prepare_and_apply_invalidates_token(mcp_env: FakeZephyr) -> None:
    plan = _plan({"case_id": "a", "action": "create", "name": "A"})
    prepared = json.loads(server.prepare_apply(plan))
    mcp_env.settings.project_key = "OTHER"
    applied = json.loads(server.apply_plan(prepared["apply_token"], plan))
    assert applied["code"] == "APPLY_TOKEN_INVALID"
    assert mcp_env.creates == []


def test_reconcile_then_resume_creates_once(mcp_env: FakeZephyr) -> None:
    plan = _plan({"case_id": "a", "action": "create", "name": "A"})
    token = json.loads(server.prepare_apply(plan))["apply_token"]
    mcp_env.create_result = {"ok": False, "status_code": 0, "outcome": "unknown", "error": "ReadTimeout"}
    first = json.loads(server.apply_plan(token, plan))
    assert first["results"][0]["status"] == "unknown"
    blocked = json.loads(server.resume_apply(token, plan))
    assert blocked["results"][0]["code"] == "RECONCILE_REQUIRED"
    reconciled = json.loads(server.reconcile_apply(token, plan, "a", "absent"))
    assert reconciled["status"] == "reconciled_absent"
    mcp_env.create_result = {"ok": True, "status_code": 201, "data": {"key": "QA-T20"}}
    resumed = json.loads(server.resume_apply(token, plan))
    assert resumed["results"][0]["zephyr_key"] == "QA-T20"
    again = json.loads(server.reconcile_apply(token, plan, "a", "absent"))
    assert again["code"] == "NOTHING_TO_RECONCILE"
    assert len(mcp_env.creates) == 2


def test_reconcile_created_verifies_name(mcp_env: FakeZephyr) -> None:
    plan = _plan({"case_id": "a", "action": "create", "name": "A"})
    token = json.loads(server.prepare_apply(plan))["apply_token"]
    mcp_env.create_result = {"ok": False, "status_code": 502, "data": None}
    server.apply_plan(token, plan)
    mcp_env.remote["QA-T30"] = {"name": "Другой кейс"}
    wrong = json.loads(server.reconcile_apply(token, plan, "a", "created", zephyr_key="QA-T30"))
    assert wrong["code"] == "RECONCILE_UNVERIFIED"
    mcp_env.remote["QA-T31"] = {"name": "A"}
    ok = json.loads(server.reconcile_apply(token, plan, "a", "created", zephyr_key="QA-T31"))
    assert ok["status"] == "success"
    resumed = json.loads(server.resume_apply(token, plan))
    assert resumed["results"][0]["already_applied"] is True
    assert resumed["results"][0]["zephyr_key"] == "QA-T31"
    assert len(mcp_env.creates) == 1


def test_subfolders_use_selected_project_id(mcp_env: FakeZephyr, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def tree(project_id: str | None = None) -> dict[str, Any]:
        seen["project_id"] = project_id
        return {"ok": True, "data": [{"id": 7, "children": [{"id": 8}]}]}

    def search(query: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        seen["query"] = query
        return {"ok": True, "data": []}

    monkeypatch.setattr(mcp_env, "get_folder_tree", tree, raising=False)
    monkeypatch.setattr(mcp_env, "search_test_cases", search, raising=False)
    refused = json.loads(server.sync_testcase_index(["7"], include_subfolders=True, project_key="OTHER"))
    assert refused["search_status"] == "index_incomplete"
    indexed = json.loads(server.sync_testcase_index(["7"], include_subfolders=True, project_key="OTHER", project_id="202"))
    assert seen["project_id"] == "202"
    assert seen["query"] == 'projectKey = "OTHER" AND folder IN (7, 8)'
    assert indexed["complete"] is True
