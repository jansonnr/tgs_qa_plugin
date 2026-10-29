from __future__ import annotations

import pytest

from zephyr_scale_mcp.apply_executor import execute_plan_operations
from zephyr_scale_mcp.plan_rules import (
    PlanRejected,
    expand_folder_scope,
    fingerprint_case,
    fingerprint_from_response,
    match_candidates,
    plan_hash,
    sync_folder_index,
    validate_plan,
)


def _plan(**overrides: object) -> dict:
    plan = {
        "search_status": "ok",
        "draft_revision": 1,
        "operations": [
            {"case_id": "c1", "action": "create", "name": "Новый кейс"},
        ],
    }
    plan.update(overrides)
    return plan


def test_unresolved_ask_blocks_plan() -> None:
    plan = _plan(
        operations=[
            {"case_id": "c1", "action": "ask", "test_case_key": "QA-T1"},
        ]
    )
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    assert caught.value.code == "ASK_UNRESOLVED"


def test_two_operations_cannot_write_one_zephyr_key() -> None:
    plan = _plan(
        operations=[
            {
                "case_id": "c1",
                "action": "update",
                "test_case_key": "QA-T1",
                "baseline_fingerprint": "aaa",
            },
            {
                "case_id": "c2",
                "action": "update",
                "test_case_key": "QA-T1",
                "baseline_fingerprint": "aaa",
            },
        ]
    )
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    assert caught.value.code == "DUPLICATE_TARGET"


def test_incomplete_search_is_not_no_match() -> None:
    plan = _plan(search_status="index_incomplete")
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    assert caught.value.code == "SEARCH_BLOCKED"


def test_plan_hash_changes_when_draft_changes() -> None:
    original = _plan()
    changed = _plan(operations=[{"case_id": "c1", "action": "create", "name": "Другое имя"}])
    assert plan_hash(original) != plan_hash(changed)


def test_match_high_overlap_asks_and_miss_is_not_no_duplicates() -> None:
    index_items = [{"key": "QA-T1", "name": "Вход с неверным паролем", "labels": []}]
    found = match_candidates(
        index_items,
        [{"case_id": "c1", "phrases": ["Вход с неверным паролем"]}],
    )
    partial = match_candidates(
        index_items,
        [{"case_id": "c3", "phrases": ["неверным паролем"]}],
    )
    missed = match_candidates(
        index_items,
        [{"case_id": "c2", "title": "Выгрузка отчёта"}],
    )
    assert found["results"][0]["suggested_action"] == "ask"
    assert partial["results"][0]["suggested_action"] == "create"
    assert missed["results"][0]["suggested_action"] == "create"
    assert missed["results"][0]["note"] == "по доступным полям похожих не найдено"


def test_skip_requires_confirmed_step_match() -> None:
    steps = [{"description": "Открыть форму", "expectedResult": "Форма открыта"}]
    index_items = [{"key": "QA-T1", "name": "Открыть форму входа", "labels": [], "steps": steps}]
    without_confirm = match_candidates(
        index_items,
        [{"case_id": "c1", "phrases": ["Открыть форму входа"], "steps": steps}],
    )
    confirmed = match_candidates(
        index_items,
        [{"case_id": "c1", "phrases": ["Открыть форму входа"], "steps": steps, "confirmed_skip": True}],
    )
    assert without_confirm["results"][0]["suggested_action"] == "ask"
    assert confirmed["results"][0]["suggested_action"] == "skip"


def test_index_marks_incomplete_when_pages_remain() -> None:
    def search(_query: str, page_size: int, start_at: int) -> dict:
        remaining = max(0, 120 - start_at)
        count = min(page_size, remaining)
        return {
            "ok": True,
            "data": {
                "total": 120,
                "results": [{"key": f"QA-T{start_at + offset}", "name": "Кейс"} for offset in range(count)],
            },
        }

    incomplete = sync_folder_index(search, query='projectKey = "QA"', page_size=50, max_pages=1)
    complete = sync_folder_index(search, query='projectKey = "QA"', page_size=50, max_pages=3)
    assert incomplete["search_status"] == "index_incomplete"
    assert complete["search_status"] == "ok"
    assert complete["complete"] is True
    assert len(complete["items"]) == 120


def test_subfolders_are_included_only_when_requested() -> None:
    tree = [{"id": 1, "children": [{"id": 2, "children": [{"id": 3}]}]}, {"id": 9}]
    assert expand_folder_scope(tree, ["1"], include_subfolders=False) == ["1"]
    assert expand_folder_scope(tree, ["1"], include_subfolders=True) == ["1", "2", "3"]


class _FakeZephyr:
    def __init__(self, remote: dict) -> None:
        self.remote = remote
        self.updates: list[str] = []

    def get_test_case(self, test_case_key: str) -> dict:
        return {"ok": True, "status_code": 200, "data": self.remote | {"key": test_case_key}}

    def update_test_case(self, test_case_key: str, **_kwargs: object) -> dict:
        self.updates.append(test_case_key)
        return {"ok": True, "status_code": 200, "data": {"key": test_case_key}}

    def create_test_case(self, **_kwargs: object) -> dict:
        raise AssertionError("create не должен вызываться")

    def delete_test_case(self, test_case_key: str) -> dict:
        raise AssertionError(test_case_key)


def test_changed_remote_case_is_not_updated() -> None:
    remote = {"name": "Старое", "testScript": {"steps": [{"id": 1, "description": "Шаг"}]}}
    baseline = fingerprint_from_response({"data": remote})
    client = _FakeZephyr({"name": "Уже изменили", "testScript": {"steps": [{"id": 1, "description": "Шаг"}]}})
    results = execute_plan_operations(
        client,  # type: ignore[arg-type]
        [
            {
                "case_id": "c1",
                "action": "update",
                "test_case_key": "QA-T1",
                "baseline_fingerprint": baseline,
                "name": "Старое",
            }
        ],
    )
    assert results[0]["status"] == "conflict"
    assert client.updates == []


def test_matching_fingerprint_updates_without_sending_case_id() -> None:
    remote = {"name": "Старое", "testScript": {"steps": [{"id": 1, "description": "Шаг"}]}}
    baseline = fingerprint_case(name="Старое", steps=[{"id": 1, "description": "Шаг"}])
    assert baseline == fingerprint_from_response({"data": remote})
    client = _FakeZephyr(remote)
    results = execute_plan_operations(
        client,  # type: ignore[arg-type]
        [
            {
                "case_id": "c1",
                "action": "update",
                "test_case_key": "QA-T1",
                "baseline_fingerprint": baseline,
                "name": "Новое имя",
            }
        ],
    )
    assert results[0]["status"] == "success"
    assert results[0]["case_id"] == "c1"
    assert client.updates == ["QA-T1"]
