from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from zephyr_scale_mcp.config import Settings, get_settings, origin_of
from zephyr_scale_mcp.data_policy import QaPathError, resolve_attachment_path
from zephyr_scale_mcp.keys import (
    UnsafeKey,
    assert_api_path,
    path_segment,
    require_case_key,
    require_numeric_id,
    require_project_key,
    require_run_key,
)

_INLINE_RETRY_SECONDS = 2.0


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        return max(0.0, when.timestamp() - time.time())


def _format_response(response: httpx.Response) -> dict[str, Any]:
    payload: Any
    text = response.text
    if not text:
        payload = None
    else:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = text
    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "url": str(response.request.url),
        "data": payload,
    }


def _normalize_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if steps is None:
        return None
    if not isinstance(steps, list):
        raise UnsafeKey("steps должен быть списком объектов.")
    normalized: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            raise UnsafeKey("Каждый шаг должен быть объектом с description.")
        item: dict[str, Any] = {
            "description": step.get("description") or step.get("step") or "",
        }
        test_data = step.get("testData", step.get("test_data"))
        expected = step.get("expectedResult", step.get("expected_result"))
        if step.get("id") is not None:
            item["id"] = step["id"]
        if test_data is not None:
            item["testData"] = test_data
        if expected is not None:
            item["expectedResult"] = expected
        normalized.append(item)
    return normalized


class ZephyrClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http = httpx.Client(timeout=60.0, follow_redirects=True)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        files: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        assert_api_path(path)
        base = self.settings.base_url.rstrip("/")
        origin_of(base)
        url = f"{base}{path}"
        parsed = urlsplit(url)
        if origin_of(f"{parsed.scheme}://{parsed.netloc}") != origin_of(base):
            raise UnsafeKey("Итоговый URL выходит за настроенный origin.")
        headers = {
            "Authorization": self.settings.auth_header(),
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",
        }
        if extra_headers:
            headers.update(extra_headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        retries_left = 3 if method.upper() == "GET" and files is None else 0
        while True:
            try:
                response = self._http.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                return {
                    "ok": False,
                    "status_code": 0,
                    "outcome": "unknown",
                    "error": type(exc).__name__,
                }
            wait = _retry_after_seconds(response) if response.status_code == 429 else None
            if (
                response.status_code == 429
                and retries_left > 0
                and wait is not None
                and wait <= _INLINE_RETRY_SECONDS
            ):
                retries_left -= 1
                time.sleep(wait)
                continue
            formatted = _format_response(response)
            if response.status_code == 429:
                formatted["retry_after"] = wait
                formatted["outcome"] = "paused"
            return formatted

    def create_test_case(
        self,
        *,
        name: str,
        objective: str | None = None,
        folder: str | None = None,
        status: str = "Draft",
        priority: str = "Normal",
        project_key: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        labels: list[str] | None = None,
        precondition: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "projectKey": project_key or self.settings.project_key,
            "name": name,
            "status": status,
            "priority": priority,
        }
        if objective is not None:
            body["objective"] = objective
        if precondition is not None:
            body["precondition"] = precondition
        if folder is not None:
            body["folder"] = folder
        if labels:
            body["labels"] = labels
        normalized = _normalize_steps(steps)
        if normalized:
            body["testScript"] = {"type": "STEP_BY_STEP", "steps": normalized}
        if extra:
            body.update(extra)
        return self.request("POST", "/rest/atm/1.0/testcase", json_body=body)

    def get_test_case(self, test_case_key: str) -> dict[str, Any]:
        result = self.request("GET", f"/rest/atm/1.0/testcase/{path_segment(require_case_key(test_case_key))}")
        if result.get("ok") is True and isinstance(result.get("data"), dict):
            from zephyr_scale_mcp.plan_rules import fingerprint_from_response

            result["baseline_fingerprint"] = fingerprint_from_response(result)
        return result

    def update_test_case(
        self,
        test_case_key: str,
        *,
        name: str | None = None,
        objective: str | None = None,
        folder: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        labels: list[str] | None = None,
        precondition: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if objective is not None:
            body["objective"] = objective
        if folder is not None:
            body["folder"] = folder
        if status is not None:
            body["status"] = status
        if priority is not None:
            body["priority"] = priority
        if precondition is not None:
            body["precondition"] = precondition
        if labels is not None:
            body["labels"] = labels
        if steps is not None:
            body["testScript"] = {"type": "STEP_BY_STEP", "steps": _normalize_steps(steps)}
        if extra:
            body.update(extra)
        return self.request("PUT", f"/rest/atm/1.0/testcase/{path_segment(require_case_key(test_case_key))}", json_body=body)

    def delete_test_case(self, test_case_key: str) -> dict[str, Any]:
        return self.request("DELETE", f"/rest/atm/1.0/testcase/{path_segment(require_case_key(test_case_key))}")

    def search_test_cases(
        self,
        query: str | None = None,
        max_results: int = 50,
        start_at: int = 0,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        q = query or f'projectKey = "{require_project_key(project_key or self.settings.project_key)}"'
        return self.request(
            "GET",
            "/rest/atm/1.0/testcase/search",
            params={"query": q, "maxResults": max_results, "startAt": start_at},
        )

    def get_latest_test_result(self, test_case_key: str) -> dict[str, Any]:
        key = path_segment(require_case_key(test_case_key))
        return self.request("GET", f"/rest/atm/1.0/testcase/{key}/testresult/latest")

    def list_test_case_attachments(self, test_case_key: str) -> dict[str, Any]:
        key = path_segment(require_case_key(test_case_key))
        return self.request("GET", f"/rest/atm/1.0/testcase/{key}/attachments")

    def upload_test_case_attachment(
        self,
        test_case_key: str,
        file_path: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        try:
            path = resolve_attachment_path(file_path)
        except QaPathError as exc:
            return {"ok": False, "status_code": 0, "error": str(exc)}
        name = filename or path.name
        key = path_segment(require_case_key(test_case_key))
        with path.open("rb") as handle:
            return self.request(
                "POST",
                f"/rest/atm/1.0/testcase/{key}/attachments",
                data={"filename": name},
                files={"file": (name, handle)},
            )

    def create_test_run(
        self,
        *,
        name: str,
        folder: str | None = None,
        description: str | None = None,
        test_case_keys: list[str] | None = None,
        project_key: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "projectKey": project_key or self.settings.project_key,
            "name": name,
        }
        if folder is not None:
            body["folder"] = folder
        if description is not None:
            body["description"] = description
        if test_case_keys:
            body["items"] = [{"testCaseKey": key} for key in test_case_keys]
        if extra:
            body.update(extra)
        return self.request("POST", "/rest/atm/1.0/testrun", json_body=body)

    def get_test_run(self, test_run_key: str) -> dict[str, Any]:
        return self.request("GET", f"/rest/atm/1.0/testrun/{path_segment(require_run_key(test_run_key))}")

    def delete_test_run(self, test_run_key: str) -> dict[str, Any]:
        return self.request("DELETE", f"/rest/atm/1.0/testrun/{path_segment(require_run_key(test_run_key))}")

    def search_test_runs(
        self,
        query: str | None = None,
        max_results: int = 50,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        q = query or f'projectKey = "{require_project_key(project_key or self.settings.project_key)}"'
        return self.request(
            "GET",
            "/rest/atm/1.0/testrun/search",
            params={"query": q, "maxResults": max_results},
        )

    def get_folder(self, folder_id: str) -> dict[str, Any]:
        folder = path_segment(require_numeric_id(folder_id, what="id папки"))
        return self.request("GET", f"/rest/tests/1.0/folder/{folder}")

    def get_folder_tree(self, project_id: str | None = None) -> dict[str, Any]:
        pid = path_segment(require_numeric_id(project_id or self.settings.project_id, what="id проекта"))
        return self.request("GET", f"/rest/tests/1.0/project/{pid}/foldertree/testcase")
