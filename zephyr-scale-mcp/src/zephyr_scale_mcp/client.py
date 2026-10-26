from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from zephyr_scale_mcp.config import Settings, get_settings


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


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
    if not steps:
        return None
    normalized: list[dict[str, Any]] = []
    for step in steps:
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
        files: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.settings.base_url.rstrip('/')}{path}"
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
            if response.status_code == 429 and retries_left > 0:
                retries_left -= 1
                time.sleep(min(_retry_after_seconds(response), 2.0))
                continue
            formatted = _format_response(response)
            if response.status_code == 429:
                formatted["retry_after"] = _retry_after_seconds(response)
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
        return self.request("GET", f"/rest/atm/1.0/testcase/{test_case_key}")

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
        if labels is not None:
            body["labels"] = labels
        normalized = _normalize_steps(steps)
        if normalized:
            body["testScript"] = {"type": "STEP_BY_STEP", "steps": normalized}
        if extra:
            body.update(extra)
        return self.request("PUT", f"/rest/atm/1.0/testcase/{test_case_key}", json_body=body)

    def delete_test_case(self, test_case_key: str) -> dict[str, Any]:
        return self.request("DELETE", f"/rest/atm/1.0/testcase/{test_case_key}")

    def search_test_cases(
        self,
        query: str | None = None,
        max_results: int = 50,
        start_at: int = 0,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        q = query or f'projectKey = "{project_key or self.settings.project_key}"'
        return self.request(
            "GET",
            "/rest/atm/1.0/testcase/search",
            params={"query": q, "maxResults": max_results, "startAt": start_at},
        )

    def get_latest_test_result(self, test_case_key: str) -> dict[str, Any]:
        return self.request("GET", f"/rest/atm/1.0/testcase/{test_case_key}/testresult/latest")

    def list_test_case_attachments(self, test_case_key: str) -> dict[str, Any]:
        return self.request("GET", f"/rest/atm/1.0/testcase/{test_case_key}/attachments")

    def upload_test_case_attachment(
        self,
        test_case_key: str,
        file_path: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path).expanduser()
        if not path.is_file():
            return {"ok": False, "status_code": 0, "error": f"Файл не найден: {path}"}
        name = filename or path.name
        with path.open("rb") as handle:
            files = {"file": (name, handle)}
            data = {"filename": name}
            url = (
                f"{self.settings.base_url.rstrip('/')}"
                f"/rest/atm/1.0/testcase/{test_case_key}/attachments"
            )
            headers = {
                "Authorization": self.settings.auth_header(),
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            }
            response = self._http.post(url, headers=headers, files=files, data=data)
        return _format_response(response)

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
        return self.request("GET", f"/rest/atm/1.0/testrun/{test_run_key}")

    def delete_test_run(self, test_run_key: str) -> dict[str, Any]:
        return self.request("DELETE", f"/rest/atm/1.0/testrun/{test_run_key}")

    def search_test_runs(
        self,
        query: str | None = None,
        max_results: int = 50,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        q = query or f'projectKey = "{project_key or self.settings.project_key}"'
        return self.request(
            "GET",
            "/rest/atm/1.0/testrun/search",
            params={"query": q, "maxResults": max_results},
        )

    def get_folder(self, folder_id: str) -> dict[str, Any]:
        return self.request("GET", f"/rest/tests/1.0/folder/{folder_id}")

    def get_folder_tree(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.settings.project_id
        return self.request("GET", f"/rest/tests/1.0/project/{pid}/foldertree/testcase")
