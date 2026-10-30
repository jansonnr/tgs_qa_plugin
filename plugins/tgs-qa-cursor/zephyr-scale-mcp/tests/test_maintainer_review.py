"""Регрессии по ревью мейнтейнера (C01–C25)."""

from __future__ import annotations

import multiprocessing
from email.utils import formatdate
from pathlib import Path

import httpx
import pytest

from zephyr_scale_mcp.apply_executor import execute_plan_operations
from zephyr_scale_mcp.apply_log import append_apply_log, latest_apply_entries
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.config import ConfigError, Settings, origin_of, update_settings
from zephyr_scale_mcp.confluence import extract_linked_page_ids
from zephyr_scale_mcp.data_policy import mask_secrets, page_text, scan_text, to_agent
from zephyr_scale_mcp.keys import UnsafeKey
from zephyr_scale_mcp.plan_rules import (
    PlanRejected,
    adapt_draft_steps,
    adapt_plan,
    fingerprint_from_response,
    match_candidates,
    operation_hash,
    plan_hash,
    run_log_key,
    sync_folder_index,
    update_changes,
    validate_plan,
)


def _hold_lock(path: str, ready: multiprocessing.Event, release: multiprocessing.Event) -> None:
    from zephyr_scale_mcp.apply_log import hold_apply_lock

    with hold_apply_lock("same-hash", Path(path)):
        ready.set()
        release.wait(10)


def _client(handler, token: str = "token") -> ZephyrClient:
    client = ZephyrClient(Settings(bearer_token=token))
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_c08_second_process_is_apply_busy(tmp_path: Path) -> None:
    from zephyr_scale_mcp.apply_log import ApplyBusy, hold_apply_lock

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    proc = ctx.Process(target=_hold_lock, args=(str(tmp_path), ready, release))
    proc.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ApplyBusy):
            with hold_apply_lock("same-hash", tmp_path):
                pass
    finally:
        release.set()
        proc.join(10)
    assert proc.exitcode == 0


def test_c20_path_traversal_never_becomes_http() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(204)

    client = _client(handler)
    with pytest.raises(UnsafeKey):
        client.delete_test_run("../../../api/2/issue/QA-1")
    with pytest.raises(UnsafeKey):
        client.delete_test_case("QA-T1/../../../../api/2/issue/QA-2")
    plan = {
        "search_status": "ok",
        "operations": [
            {"case_id": "c1", "action": "delete", "test_case_key": "../../../api/2/issue/QA-1"},
        ],
    }
    with pytest.raises(PlanRejected):
        validate_plan(plan)
    assert calls["n"] == 0


def test_c22_origin_change_drops_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import zephyr_scale_mcp.config as config

    monkeypatch.setattr(config, "_runtime", None)
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setenv("ZEPHYR_TRUSTED_ORIGINS", "https://trusted.invalid")
    update_settings(base_url="https://trusted.invalid/soft", bearer_token="synthetic-token-value")
    monkeypatch.delenv("ZEPHYR_TRUSTED_ORIGINS", raising=False)
    with pytest.raises(ConfigError):
        update_settings(base_url="http://other.invalid")
    assert origin_of(config.get_settings().base_url) == "https://trusted.invalid"
    assert config.get_settings().bearer_token == "synthetic-token-value"
    monkeypatch.setenv("ZEPHYR_TRUSTED_ORIGINS", "https://other.invalid")
    update_settings(base_url="https://other.invalid/jira")
    assert config.get_settings().bearer_token == ""


def test_wiki_origin_change_requires_trusted_origins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import zephyr_scale_mcp.config as config

    monkeypatch.setattr(config, "_runtime", None)
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setenv("ZEPHYR_TRUSTED_ORIGINS", "https://track.example,https://evil.example")
    update_settings(
        base_url="https://track.example/soft",
        wiki_bearer_token="wiki-token-value",
    )
    monkeypatch.delenv("ZEPHYR_TRUSTED_ORIGINS", raising=False)
    with pytest.raises(ConfigError):
        update_settings(wiki_url="https://evil.example/wiki")
    assert config.get_settings().wiki_bearer_token == "wiki-token-value"
    monkeypatch.setenv("ZEPHYR_TRUSTED_ORIGINS", "https://evil.example")
    update_settings(wiki_url="https://evil.example/wiki")
    assert config.get_settings().wiki_bearer_token == ""


def test_c02_pem_and_bearer_are_fully_masked() -> None:
    first = "-----BEGIN PRIVATE KEY-----\nFAKE_BODY_A\n-----END PRIVATE KEY-----"
    second = "-----BEGIN PRIVATE KEY-----\nFAKE_BODY_B\n-----END PRIVATE KEY-----"
    masked, count = mask_secrets(first)
    assert "FAKE_BODY_A" not in masked
    assert count == 1
    ids = {item["id"] for item in scan_text(first + "\n" + second)}
    assert len(ids) == 2
    plus = "Bearer abcdefghijklmnopqrstuv+wxyz0123/ABC="
    slash = "Bearer abcd+efghijklmnopqrstuv/wxyz0123="
    assert "abcdefghijklmnopqrstuv" not in mask_secrets(plus)[0]
    assert "wxyz0123" not in mask_secrets(slash)[0]


def test_c21_auth_stop_does_not_replay_success(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.phase = 1
            self.creates: list[str] = []

        def create_test_case(self, **kwargs: object) -> dict:
            name = str(kwargs["name"])
            self.creates.append(name)
            if name == "A":
                return {"ok": False, "status_code": 400 if self.phase == 1 else 401, "data": {}}
            return {"ok": True, "status_code": 201, "data": {"key": "QA-T2"}}

    client = Client()
    operations = [
        {"case_id": "a", "action": "create", "name": "A"},
        {"case_id": "b", "action": "create", "name": "B"},
    ]
    execute_plan_operations(client, operations, plan_hash="batch", log_root=tmp_path)  # type: ignore[arg-type]
    client.phase = 2
    execute_plan_operations(client, operations, plan_hash="batch", log_root=tmp_path)  # type: ignore[arg-type]
    client.phase = 3
    third = execute_plan_operations(client, operations, plan_hash="batch", log_root=tmp_path)  # type: ignore[arg-type]
    assert third[1]["already_applied"] is True
    assert client.creates.count("B") == 1


def test_c03_started_create_is_not_repeated(tmp_path: Path) -> None:
    operation = {"case_id": "a", "action": "create", "name": "A"}
    append_apply_log(
        "crash",
        {
            "case_id": "a",
            "action": "create",
            "status": "started",
            "op_hash": operation_hash(operation),
        },
        tmp_path,
    )

    class Client:
        def __init__(self) -> None:
            self.creates = 0

        def create_test_case(self, **_kwargs: object) -> dict:
            self.creates += 1
            return {"ok": True, "status_code": 201, "data": {"key": "QA-T1"}}

    client = Client()
    result = execute_plan_operations(
        client,  # type: ignore[arg-type]
        [operation],
        plan_hash="crash",
        log_root=tmp_path,
    )
    assert result[0]["code"] == "RECONCILE_REQUIRED"
    assert client.creates == 0


def test_c04_unchanged_neighbor_is_not_recreated(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.names: list[str] = []

        def create_test_case(self, **kwargs: object) -> dict:
            name = str(kwargs["name"])
            self.names.append(name)
            if name.startswith("Two"):
                return {"ok": False, "status_code": 400, "data": {}}
            return {"ok": True, "status_code": 201, "data": {"key": "QA-T1"}}

    client = Client()
    first = [
        {"case_id": "one", "action": "create", "name": "One"},
        {"case_id": "two", "action": "create", "name": "Two"},
    ]
    second = [
        {"case_id": "one", "action": "create", "name": "One"},
        {"case_id": "two", "action": "create", "name": "Two corrected"},
    ]
    execute_plan_operations(client, first, plan_hash="same-run", log_root=tmp_path)  # type: ignore[arg-type]
    execute_plan_operations(client, second, plan_hash="same-run", log_root=tmp_path)  # type: ignore[arg-type]
    assert client.names.count("One") == 1
    assert "Two corrected" in client.names


def test_c05_run_identity_is_part_of_hash_and_log() -> None:
    left = {"search_status": "ok", "run_id": "run-a", "qa_root": "C:/a/.qa", "operations": [{"case_id": "c", "action": "create", "name": "A"}]}
    right = {"search_status": "ok", "run_id": "run-b", "qa_root": "C:/b/.qa", "operations": [{"case_id": "c", "action": "create", "name": "A"}]}
    assert plan_hash(left) != plan_hash(right)
    assert run_log_key(left, origin="https://trusted.invalid", project_key="QA") != run_log_key(
        right, origin="https://trusted.invalid", project_key="QA"
    )
    assert plan_hash(left) != plan_hash(left, target={"origin": "https://other.invalid", "project_key": "QA"})


def test_c07_fingerprint_covers_objective(tmp_path: Path) -> None:
    remote = {"name": "Order", "objective": "Changed", "priority": "High", "testScript": {"steps": []}}
    baseline = fingerprint_from_response({"data": {"name": "Order", "objective": "Original", "priority": "Normal", "testScript": {"steps": []}}})
    assert baseline != fingerprint_from_response({"data": remote})


def test_c06_short_page_and_html_are_not_complete() -> None:
    def short(_query: str, page_size: int, _start: int) -> dict:
        assert page_size == 50
        return {"ok": True, "data": {"total": 100, "results": [{"key": "QA-T1", "name": "A"}] * 20}}

    def html(_query: str, _page_size: int, _start: int) -> dict:
        return {"ok": True, "data": "<html>login</html>"}

    indexed = sync_folder_index(short, query="projectKey = QA", page_size=50)
    assert indexed["complete"] is False
    assert indexed["search_status"] == "index_incomplete"
    broken = sync_folder_index(html, query="projectKey = QA")
    assert broken["complete"] is False
    assert broken["search_status"] == "api_error"


def test_c11_case_change_is_a_real_diff() -> None:
    remote = {"ok": True, "data": {"name": "ok", "testScript": {"steps": [{"description": "step"}]}}}
    changes = update_changes({"name": "OK", "steps": [{"description": "STEP"}]}, remote)
    assert changes["name"] == "OK"
    assert changes["steps"][0]["description"] == "STEP"


def test_c12_empty_steps_are_sent() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"key": "QA-T1"})

    client = _client(handler)
    client.update_test_case("QA-T1", steps=[])
    omitted = _client(lambda _request: httpx.Response(200, json={"key": "QA-T1"}))
    seen_omit: dict = {}

    def handler_omit(request: httpx.Request) -> httpx.Response:
        seen_omit["body"] = request.read()
        return httpx.Response(200, json={"key": "QA-T1"})

    omitted._http = httpx.Client(transport=httpx.MockTransport(handler_omit))
    omitted.update_test_case("QA-T1", name="Same")
    assert b"testScript" in seen["body"]
    assert b"testScript" not in seen_omit["body"]


def test_c25_string_steps_rejected_before_apply() -> None:
    plan = {
        "search_status": "ok",
        "operations": [{"case_id": "c1", "action": "create", "name": "A", "steps": ["Open", "Click"]}],
    }
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    assert caught.value.code == "PLAN_INVALID"


def test_c23_config_error_is_not_sent(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(201, json={"key": "QA-T1"})

    client = _client(handler, token="")
    first = execute_plan_operations(
        client,
        [{"case_id": "c1", "action": "create", "name": "A"}],
        plan_hash="cfg",
        log_root=tmp_path,
    )
    assert first[0]["status"] == "not_sent"
    assert calls["n"] == 0
    client.settings.bearer_token = "token"
    second = execute_plan_operations(
        client,
        [{"case_id": "c1", "action": "create", "name": "A"}],
        plan_hash="cfg",
        log_root=tmp_path,
    )
    assert second[0]["status"] == "success"
    assert calls["n"] == 1


def test_c24_corrupt_log_keeps_successful_lines(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(
        '{"case_id":"a","action":"create","status":"success","zephyr_key":"QA-T1"}\n'
        '{"case_id":"b","act\n',
        encoding="utf-8",
    )
    found, corrupt = latest_apply_entries("broken", tmp_path)
    assert corrupt is True
    assert found[("a", "create")]["status"] == "success"


def test_c19_create_without_key_needs_reconcile(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.creates = 0

        def create_test_case(self, **_kwargs: object) -> dict:
            self.creates += 1
            return {"ok": True, "status_code": 201, "data": None}

    client = Client()
    operations = [{"case_id": "c1", "action": "create", "name": "A"}]
    first = execute_plan_operations(client, operations, plan_hash="nokey", log_root=tmp_path)  # type: ignore[arg-type]
    second = execute_plan_operations(client, operations, plan_hash="nokey", log_root=tmp_path)  # type: ignore[arg-type]
    assert first[0]["status"] == "unknown"
    assert second[0]["code"] == "RECONCILE_REQUIRED"
    assert client.creates == 1


def test_c14_rate_limit_stops_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"post": 0, "slept": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["post"] += 1
            return httpx.Response(429, headers={"Retry-After": "120"}, json={"error": "slow"})
        return httpx.Response(429, headers={"Retry-After": formatdate(1_700_000_120, usegmt=True)})

    monkeypatch.setattr("zephyr_scale_mcp.client.time.sleep", lambda seconds: calls["slept"].append(seconds))
    monkeypatch.setattr("zephyr_scale_mcp.client.time.time", lambda: 1_700_000_000)
    client = _client(handler)

    class Batch:
        def __init__(self) -> None:
            self.client = client
            self.creates = 0

        def create_test_case(self, **kwargs: object) -> dict:
            self.creates += 1
            return self.client.create_test_case(**kwargs)

    batch = Batch()
    results = execute_plan_operations(
        batch,  # type: ignore[arg-type]
        [
            {"case_id": "c1", "action": "create", "name": "A"},
            {"case_id": "c2", "action": "create", "name": "B"},
            {"case_id": "c3", "action": "create", "name": "C"},
        ],
    )
    assert calls["post"] == 1
    assert results[0]["status"] == "paused"
    assert results[1]["status"] == "not_run"
    fetched = client.get_test_case("QA-T1")
    assert fetched["outcome"] == "paused"
    assert fetched["retry_after"] == pytest.approx(120)
    assert calls["slept"] == []


def test_c09_exact_name_survives_extra_metadata() -> None:
    bare = match_candidates(
        [{"key": "QA-T1", "name": "Login valid password"}],
        [{"case_id": "c1", "phrases": ["Login valid password"]}],
    )
    rich = match_candidates(
        [{"key": "QA-T1", "name": "Login valid password", "objective": "word " * 80, "labels": ["smoke"]}],
        [{"case_id": "c1", "phrases": ["Login valid password"]}],
    )
    assert bare["results"][0]["suggested_action"] == "ask"
    assert rich["results"][0]["candidates"]
    assert rich["results"][0]["suggested_action"] == "ask"


def test_c15_different_data_is_not_equivalent() -> None:
    steps = [{"description": "Open", "expectedResult": "Form", "testData": "visa"}]
    other = [{"description": "Open", "expectedResult": "Form", "testData": "mastercard"}]
    found = match_candidates(
        [{"key": "QA-T1", "name": "Pay", "steps": steps}],
        [{"case_id": "c1", "phrases": ["Pay"], "steps": other, "confirmed_skip": True}],
    )
    assert found["results"][0]["suggested_action"] != "skip"


def test_c16_link_uses_space_key() -> None:
    seen: dict[str, str] = {}

    def lookup(title: str, space_key: str | None = None) -> str | None:
        seen["title"] = title
        seen["space"] = space_key or ""
        return "99" if space_key == "PAY" else None

    html = '<ac:link><ri:page ri:content-title="Shared title" ri:space-key="PAY" /></ac:link>'
    assert list(extract_linked_page_ids(html, lookup=lookup)) == ["99"]
    assert seen["space"] == "PAY"


def test_c17_text_can_be_read_in_pages() -> None:
    body = "начало " + ("требование " * 800) + "КОНЕЦ"
    first = page_text(body, offset=0)
    assert first["complete"] is False
    assert "КОНЕЦ" not in first["text"]
    rest = page_text(body, offset=first["next_offset"])
    assert "КОНЕЦ" in rest["text"] or rest["complete"] is False
    public = to_agent({"ok": True, "content_markdown": body})
    assert public["context"]["truncated"] == 1
    assert public["content_markdown"].endswith("…")


def test_c01_example_shapes_adapt() -> None:
    adapted = adapt_plan(
        {
            "search_status": "complete",
            "draft_revision": 1,
            "items": [
                {"draft_id": "2", "draft_name": "Отказ банка", "action": "create", "target_key": None},
            ],
        }
    )
    validate_plan(adapted)
    steps = adapt_draft_steps(
        {
            "steps": ["Открыть"],
            "test_data": ["visa"],
            "expected_results": ["Форма"],
        }
    )
    assert steps == [{"description": "Открыть", "testData": "visa", "expectedResult": "Форма"}]
    found = match_candidates(
        [{"key": "QA-T1", "name": "Успешная оплата банковской картой"}],
        [{"draft_id": "1", "name": "Успешная оплата банковской картой"}],
    )
    assert found["results"][0]["case_id"] == "1"
    assert found["results"][0]["suggested_action"] == "ask"


def test_c10_precondition_is_written(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        def create_test_case(self, **kwargs: object) -> dict:
            self.kwargs = kwargs
            return {"ok": True, "status_code": 201, "data": {"key": "QA-T3"}}

    client = Client()
    execute_plan_operations(
        client,  # type: ignore[arg-type]
        [{"case_id": "c1", "action": "create", "name": "A", "precondition": "Пользователь вошёл"}],
        plan_hash="pre",
        log_root=tmp_path,
    )
    assert client.kwargs["precondition"] == "Пользователь вошёл"
    assert client.kwargs["labels"] == ["AI_Cursor"]


def test_c13_secret_placeholder_is_not_written_back() -> None:
    secret = "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    remote = {"ok": True, "data": {"name": "Case", "objective": f"Токен {secret}", "testScript": {"steps": []}}}
    changes = update_changes({"name": "Case", "objective": "Токен [secret]"}, remote)
    assert "objective" not in changes
