from __future__ import annotations

from pathlib import Path

import httpx

from zephyr_scale_mcp.apply_executor import execute_plan_operations
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.config import Settings


class _CreateClient:
    def __init__(self) -> None:
        self.creates = 0

    def create_test_case(self, **_kwargs: object) -> dict:
        self.creates += 1
        if self.creates == 1:
            return {"ok": False, "status_code": 0, "outcome": "unknown", "error": "TimeoutException"}
        return {"ok": True, "status_code": 201, "data": {"key": "QA-T9"}}

    def get_test_case(self, test_case_key: str) -> dict:
        raise AssertionError(test_case_key)

    def update_test_case(self, *_args: object, **_kwargs: object) -> dict:
        raise AssertionError("update")

    def delete_test_case(self, test_case_key: str) -> dict:
        raise AssertionError(test_case_key)


def test_unknown_create_is_not_repeated(tmp_path: Path) -> None:
    client = _CreateClient()
    operations = [{"case_id": "c1", "action": "create", "name": "Новый"}]
    first = execute_plan_operations(client, operations, plan_hash="plan-a", log_root=tmp_path)  # type: ignore[arg-type]
    second = execute_plan_operations(client, operations, plan_hash="plan-a", log_root=tmp_path)  # type: ignore[arg-type]
    assert first[0]["status"] == "unknown"
    assert second[0]["code"] == "RECONCILE_REQUIRED"
    assert client.creates == 1


def test_auth_error_stops_the_rest_of_the_batch() -> None:
    class Client:
        def create_test_case(self, **_kwargs: object) -> dict:
            return {"ok": False, "status_code": 401, "data": {"message": "nope"}}

        def get_test_case(self, test_case_key: str) -> dict:
            raise AssertionError(test_case_key)

        def update_test_case(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("update")

        def delete_test_case(self, test_case_key: str) -> dict:
            raise AssertionError(test_case_key)

    results = execute_plan_operations(
        Client(),  # type: ignore[arg-type]
        [
            {"case_id": "c1", "action": "create", "name": "Первый"},
            {"case_id": "c2", "action": "create", "name": "Второй"},
        ],
    )
    assert results[0]["code"] == "AUTH_STOPPED"
    assert results[1]["status"] == "not_run"


def test_successful_operation_is_not_sent_again(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.creates = 0

        def create_test_case(self, **_kwargs: object) -> dict:
            self.creates += 1
            return {"ok": True, "status_code": 201, "data": {"key": "QA-T2"}}

        def get_test_case(self, test_case_key: str) -> dict:
            raise AssertionError(test_case_key)

        def update_test_case(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("update")

        def delete_test_case(self, test_case_key: str) -> dict:
            raise AssertionError(test_case_key)

    client = Client()
    operations = [{"case_id": "c1", "action": "create", "name": "Готово"}]
    execute_plan_operations(client, operations, plan_hash="plan-b", log_root=tmp_path)  # type: ignore[arg-type]
    again = execute_plan_operations(client, operations, plan_hash="plan-b", log_root=tmp_path)  # type: ignore[arg-type]
    assert again[0]["already_applied"] is True
    assert client.creates == 1


def test_get_retries_429_and_post_does_not(monkeypatch) -> None:
    calls = {"get": 0, "post": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            calls["get"] += 1
            if calls["get"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})
            return httpx.Response(200, json={"key": "QA-T1", "name": "Кейс"})
        calls["post"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})

    monkeypatch.setattr("zephyr_scale_mcp.client.time.sleep", lambda _seconds: None)
    client = ZephyrClient(Settings(bearer_token="token"))
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    fetched = client.get_test_case("QA-T1")
    created = client.create_test_case(name="Новый")
    assert fetched["ok"] is True
    assert calls["get"] == 2
    assert created["ok"] is False
    assert created["retry_after"] == 0
    assert calls["post"] == 1


def test_timeout_is_unknown_and_does_not_raise() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = ZephyrClient(Settings(bearer_token="token"))
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    result = client.create_test_case(name="Новый")
    assert result["outcome"] == "unknown"
    assert result["status_code"] == 0
