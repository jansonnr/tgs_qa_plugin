from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

HIGH_NAME_SCORE = 0.95
SKIP_STEP_SCORE = 0.95
MAX_CANDIDATES = 10
NO_MATCH_NOTE = "по доступным полям похожих не найдено"
ALLOWED_SEARCH = {"ok", "ok_with_limited_index"}
BLOCKING_SEARCH = {"api_error", "index_incomplete", "cache_stale"}
_TOKEN = re.compile(r"[\w\d]+", flags=re.UNICODE)
_HASH_FIELDS = (
    "action",
    "resolved_action",
    "case_id",
    "test_case_key",
    "baseline_fingerprint",
    "name",
    "objective",
    "precondition",
    "folder",
    "status",
    "priority",
    "project_key",
    "labels",
    "steps",
)


class PlanRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def effective_action(operation: dict[str, Any]) -> str:
    action = operation.get("action")
    if action == "ask":
        resolved = operation.get("resolved_action")
        return str(resolved) if resolved else "ask"
    return str(action)


def validate_plan(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict):
        raise PlanRejected("PLAN_INVALID", "plan должен быть объектом.")
    search_status = plan.get("search_status")
    if search_status not in ALLOWED_SEARCH | BLOCKING_SEARCH:
        raise PlanRejected(
            "PLAN_INVALID",
            "Укажи search_status: ok, ok_with_limited_index, api_error, index_incomplete или cache_stale.",
        )
    if search_status in BLOCKING_SEARCH:
        raise PlanRejected(
            "SEARCH_BLOCKED",
            f"Поиск в статусе {search_status} не позволяет запись. Это не «совпадений нет».",
        )
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise PlanRejected("PLAN_INVALID", "operations не может быть пустым.")

    seen_case_ids: set[str] = set()
    seen_targets: dict[str, str] = {}
    for operation in operations:
        if not isinstance(operation, dict):
            raise PlanRejected("PLAN_INVALID", "Каждая операция должна быть объектом.")
        case_id = str(operation.get("case_id") or "").strip()
        if not case_id:
            raise PlanRejected("PLAN_INVALID", "У каждой операции нужен внутренний case_id. В Zephyr он не отправляется.")
        if case_id in seen_case_ids:
            raise PlanRejected("PLAN_INVALID", f"case_id {case_id} повторяется в плане.")
        seen_case_ids.add(case_id)

        action = effective_action(operation)
        if operation.get("action") == "ask" and action not in {"create", "update", "skip"}:
            raise PlanRejected("ASK_UNRESOLVED", "Нерешённый ask блокирует весь план.")
        if action not in {"create", "update", "skip", "delete"}:
            raise PlanRejected("PLAN_INVALID", f"Неизвестное action: {operation.get('action')!r}.")
        if action == "create" and not str(operation.get("name") or "").strip():
            raise PlanRejected("PLAN_INVALID", f"Для create у {case_id} нужно name.")
        if action in {"update", "delete"}:
            target = str(operation.get("test_case_key") or "").strip()
            if not target:
                raise PlanRejected("PLAN_INVALID", f"Для {action} у {case_id} нужен test_case_key.")
            if action == "update" and not str(operation.get("baseline_fingerprint") or "").strip():
                raise PlanRejected(
                    "PLAN_INVALID",
                    f"Для update у {case_id} нужен baseline_fingerprint снимка, по которому строился diff.",
                )
            previous = seen_targets.get(target)
            if previous is not None:
                raise PlanRejected(
                    "DUPLICATE_TARGET",
                    f"Несколько операций пишут в один кейс {target}: {previous} и {case_id}.",
                )
            seen_targets[target] = case_id
        _validate_operation_shape(operation, case_id, action)
    from zephyr_scale_mcp.data_policy import enforce_secret_decisions

    enforce_secret_decisions(plan)


def _validate_operation_shape(operation: dict[str, Any], case_id: str, action: str) -> None:
    from zephyr_scale_mcp.keys import UnsafeKey, require_case_key

    for field in ("status", "priority", "name", "objective", "precondition", "folder"):
        if field in operation and operation[field] is not None and not isinstance(operation[field], str):
            raise PlanRejected("PLAN_INVALID", f"У {case_id} поле {field} должно быть строкой.")
    if "steps" in operation and operation["steps"] is not None:
        steps = operation["steps"]
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise PlanRejected(
                "PLAN_INVALID",
                f"У {case_id} steps — список объектов с description, а не строк.",
            )
    if action in {"update", "delete"}:
        try:
            require_case_key(operation.get("test_case_key"))
        except UnsafeKey as exc:
            raise PlanRejected("PLAN_INVALID", str(exc)) from exc


_STATUS_ALIASES = {
    "complete": "ok",
    "incomplete": "index_incomplete",
    "error": "api_error",
}


def adapt_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Приводит пример dedupe-plan и черновик к контракту validate_plan."""
    if not isinstance(plan, dict):
        return plan
    adapted = dict(plan)
    status = adapted.get("search_status")
    if isinstance(status, str) and status in _STATUS_ALIASES:
        adapted["search_status"] = _STATUS_ALIASES[status]
    if not isinstance(adapted.get("operations"), list):
        items = adapted.get("items")
        if isinstance(items, list):
            adapted["operations"] = [_adapt_item(item) for item in items]
    else:
        adapted["operations"] = [_adapt_item(item) for item in adapted["operations"]]
    return adapted


def adapt_draft_steps(case: dict[str, Any]) -> list[dict[str, Any]]:
    steps = case.get("steps") or []
    if not isinstance(steps, list):
        return []
    if steps and isinstance(steps[0], dict):
        return [step for step in steps if isinstance(step, dict)]
    data = case.get("test_data") or []
    expected = case.get("expected_results") or []
    structured: list[dict[str, Any]] = []
    for index, description in enumerate(steps):
        item: dict[str, Any] = {"description": str(description)}
        if index < len(data) and data[index] not in (None, "", "—"):
            item["testData"] = data[index]
        if index < len(expected) and expected[index] is not None:
            item["expectedResult"] = expected[index]
        structured.append(item)
    return structured


def _adapt_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    operation = dict(item)
    if not operation.get("case_id") and operation.get("draft_id"):
        operation["case_id"] = str(operation["draft_id"])
    if not operation.get("name") and operation.get("draft_name"):
        operation["name"] = operation["draft_name"]
    if not operation.get("test_case_key") and operation.get("target_key"):
        operation["test_case_key"] = operation["target_key"]
    if isinstance(operation.get("steps"), list) and operation["steps"] and isinstance(operation["steps"][0], str):
        operation["steps"] = adapt_draft_steps(operation)
    if operation.get("precondition") is None and isinstance(operation.get("preconditions"), list):
        operation["precondition"] = "\n".join(str(line) for line in operation["preconditions"])
    return operation


def plan_hash(plan: dict[str, Any], *, target: dict[str, str] | None = None) -> str:
    operations = []
    for operation in plan.get("operations") or []:
        if isinstance(operation, dict):
            operations.append({key: operation[key] for key in _HASH_FIELDS if key in operation})
    canonical = {
        "draft_revision": plan.get("draft_revision"),
        "search_status": plan.get("search_status"),
        "run_id": plan.get("run_id"),
        "qa_root": plan.get("qa_root"),
        "secret_decisions": plan.get("secret_decisions") or {},
        "operations": operations,
    }
    if target is not None:
        canonical["target"] = target
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def run_log_key(plan: dict[str, Any], *, origin: str, project_key: str) -> str:
    """Журнал одного запуска. Не зависит от текста соседних операций."""
    payload = {
        "origin": origin,
        "project_key": project_key,
        "run_id": str(plan.get("run_id") or ""),
        "qa_root": str(plan.get("qa_root") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def operation_hash(operation: dict[str, Any]) -> str:
    payload = {key: operation[key] for key in _HASH_FIELDS if key in operation}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def fingerprint_case(
    *,
    name: str | None,
    steps: list[dict[str, Any]] | None,
    objective: str | None = None,
    folder: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    precondition: str | None = None,
    labels: list[Any] | None = None,
) -> str:
    normalized: list[dict[str, Any]] = []
    for step in steps or []:
        normalized.append(
            {
                "id": step.get("id"),
                "description": step.get("description") or step.get("step") or "",
                "testData": step.get("testData", step.get("test_data")),
                "expectedResult": step.get("expectedResult", step.get("expected_result")),
            }
        )
    payload = {
        "name": name or "",
        "objective": objective or "",
        "folder": folder or "",
        "status": status or "",
        "priority": priority or "",
        "precondition": precondition or "",
        "labels": [str(label) for label in (labels or [])],
        "steps": normalized,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _step_text(step: dict[str, Any]) -> tuple[str, str, str]:
    description = step.get("description") or step.get("step") or ""
    test_data = step.get("testData", step.get("test_data")) or ""
    expected = step.get("expectedResult", step.get("expected_result")) or ""

    def norm(value: Any) -> str:
        return " ".join(str(value).split()).casefold()

    return (norm(description), norm(test_data), norm(expected))


def merge_steps_for_update(
    remote_steps: list[dict[str, Any]],
    draft_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Сохраняет id неизменённых шагов Zephyr. Отредактированный шаг получает id оставшегося шага, если такой один."""
    remote = [step for step in remote_steps if isinstance(step, dict)]
    draft = [step for step in draft_steps if isinstance(step, dict)]
    used: set[int] = set()
    paired: list[int | None] = [None] * len(draft)
    remote_by_id = {step.get("id"): index for index, step in enumerate(remote) if step.get("id") is not None}
    for draft_index, step in enumerate(draft):
        remote_index = remote_by_id.get(step.get("id"))
        if remote_index is not None and remote_index not in used:
            paired[draft_index] = remote_index
            used.add(remote_index)
    for draft_index, step in enumerate(draft):
        if paired[draft_index] is not None:
            continue
        signature = _step_text(step)
        for remote_index, remote_step in enumerate(remote):
            if remote_index in used or _step_text(remote_step) != signature:
                continue
            paired[draft_index] = remote_index
            used.add(remote_index)
            break
    draft_left = [index for index, remote_index in enumerate(paired) if remote_index is None]
    remote_left = [index for index in range(len(remote)) if index not in used]
    if len(draft_left) == len(remote_left):
        for draft_index, remote_index in zip(draft_left, remote_left, strict=True):
            paired[draft_index] = remote_index
    merged: list[dict[str, Any]] = []
    for draft_index, step in enumerate(draft):
        item: dict[str, Any] = {"description": step.get("description") or step.get("step") or ""}
        test_data = step.get("testData", step.get("test_data"))
        expected = step.get("expectedResult", step.get("expected_result"))
        if test_data is not None:
            item["testData"] = test_data
        if expected is not None:
            item["expectedResult"] = expected
        remote_index = paired[draft_index]
        if remote_index is not None and remote[remote_index].get("id") is not None:
            item["id"] = remote[remote_index]["id"]
        merged.append(item)
    return merged


def _exact(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _same_published_value(draft: Any, remote: Any) -> bool:
    left = _exact(draft)
    right = _exact(remote)
    if left == right:
        return True
    if left == "[secret]":
        return True
    if left.endswith("…") and right.startswith(left[:-1]):
        return True
    return False


def _step_exact(step: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _exact(step.get("description") or step.get("step")),
        _exact(step.get("testData", step.get("test_data"))),
        _exact(step.get("expectedResult", step.get("expected_result"))),
    )


def _steps_changed(remote_steps: list[dict[str, Any]], merged: list[dict[str, Any]]) -> bool:
    if len(remote_steps) != len(merged):
        return True
    for remote_step, draft_step in zip(remote_steps, merged, strict=True):
        if remote_step.get("id") != draft_step.get("id"):
            return True
        if _step_exact(remote_step) != _step_exact(draft_step):
            return True
    return False


def update_changes(operation: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    data = remote.get("data") if isinstance(remote.get("data"), dict) else remote
    if not isinstance(data, dict):
        data = {}
    changes: dict[str, Any] = {}
    for field in ("name", "objective", "folder", "status", "priority", "precondition"):
        if field not in operation or operation[field] is None:
            continue
        if not _same_published_value(operation[field], data.get(field)):
            changes[field] = operation[field]
    if operation.get("labels") is not None:
        want = [str(x).strip() for x in operation["labels"] if str(x).strip()]
        have = [str(x).strip() for x in (data.get("labels") or []) if str(x).strip()]
        if sorted(want) != sorted(have):
            changes["labels"] = want
    if operation.get("steps") is not None:
        script = data.get("testScript") if isinstance(data.get("testScript"), dict) else {}
        remote_steps = script.get("steps") if isinstance(script.get("steps"), list) else []
        merged = merge_steps_for_update(remote_steps, operation["steps"])
        if _steps_changed(remote_steps, merged):
            changes["steps"] = merged
    return changes


def fingerprint_from_response(response: dict[str, Any]) -> str:
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    if not isinstance(data, dict):
        data = {}
    script = data.get("testScript") if isinstance(data.get("testScript"), dict) else {}
    steps = script.get("steps") if isinstance(script.get("steps"), list) else data.get("steps")
    labels = data.get("labels") if isinstance(data.get("labels"), list) else []
    return fingerprint_case(
        name=data.get("name"),
        steps=steps if isinstance(steps, list) else [],
        objective=data.get("objective"),
        folder=data.get("folder"),
        status=data.get("status"),
        priority=data.get("priority"),
        precondition=data.get("precondition"),
        labels=labels,
    )


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower().replace("_", " ")) if token}


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _phrase_score(phrases: list[str], item: dict[str, Any]) -> float:
    name_tokens = _tokens(str(item.get("name") or ""))
    blob = set(name_tokens)
    for label in item.get("labels") or []:
        blob |= _tokens(str(label))
    for field in ("objective", "precondition"):
        if item.get(field):
            blob |= _tokens(str(item[field]))
    best = 0.0
    for phrase in phrases:
        phrase_tokens = _tokens(phrase)
        best = max(best, _overlap(phrase_tokens, blob))
    return best


def _step_score(draft_steps: list[dict[str, Any]], candidate_steps: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Сравнение по порядку, данным и ожидаемому результату. Перестановки не считаются тем же сценарием."""
    if not draft_steps or not candidate_steps:
        return 0.0, []
    notes: list[str] = []
    if len(draft_steps) != len(candidate_steps):
        notes.append("разная длина списка шагов")
    total = 0.0
    limit = min(len(draft_steps), len(candidate_steps))
    for index in range(limit):
        if _step_exact(draft_steps[index]) == _step_exact(candidate_steps[index]):
            total += 1.0
            continue
        notes.append(f"шаг {index + 1} отличается данными, ожиданием или текстом")
        left = _tokens(" ".join(_step_exact(draft_steps[index])))
        right = _tokens(" ".join(_step_exact(candidate_steps[index])))
        total += min(_overlap(left, right), 0.99)
    return total / max(len(draft_steps), len(candidate_steps)), notes


def match_candidates(index_items: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        phrases = [str(phrase) for phrase in (case.get("phrases") or []) if str(phrase).strip()]
        if not phrases and case.get("title"):
            phrases = [str(case["title"])]
        if not phrases and case.get("name"):
            phrases = [str(case["name"])]
        case_id = case.get("case_id") or case.get("draft_id")
        ranked: list[dict[str, Any]] = []
        step_notes: list[str] = []
        for item in index_items:
            exact_name = any(_exact(phrase).casefold() == _exact(item.get("name")).casefold() for phrase in phrases)
            name_score = max((_overlap(_tokens(phrase), _tokens(str(item.get("name") or ""))) for phrase in phrases), default=0.0)
            if not exact_name and name_score < HIGH_NAME_SCORE:
                continue
            row: dict[str, Any] = {
                "key": item.get("key"),
                "name": item.get("name"),
                "name_score": 1.0 if exact_name else round(name_score, 4),
            }
            if case.get("steps") and item.get("steps"):
                score, notes = _step_score(case["steps"], item["steps"])
                row["step_score"] = round(score, 4)
                if notes and not step_notes:
                    step_notes = notes
            ranked.append(row)
        ranked.sort(key=lambda row: (row["name_score"], row.get("step_score") or 0), reverse=True)
        shortlist = ranked[:MAX_CANDIDATES]
        if not shortlist:
            suggestion = "create"
            note = NO_MATCH_NOTE
        else:
            best = shortlist[0]
            step_score = best.get("step_score")
            equivalent = step_score is not None and step_score >= SKIP_STEP_SCORE and not step_notes
            if case.get("confirmed_skip") is True and equivalent:
                suggestion = "skip"
                note = "skip только при совпадении шагов, данных, ожиданий, порядка и явном confirmed_skip."
            else:
                suggestion = "ask"
                note = "Высокое совпадение по доступным полям. update или skip выбирает человек."
                if step_notes:
                    note = note + " Отличия: " + "; ".join(step_notes) + "."
        results.append(
            {
                "case_id": case_id,
                "suggested_action": suggestion,
                "note": note,
                "candidates": shortlist,
            }
        )
    return {"ok": True, "results": results}


def extract_search_page(response: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, int | None]:
    data = response.get("data")
    rows: list[Any]
    total: int | None = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and any(key in data for key in ("results", "values", "testCases", "total")):
        found = data.get("results") or data.get("values") or data.get("testCases") or []
        if not isinstance(found, list):
            return None, None
        rows = found
        if isinstance(data.get("total"), int):
            total = data["total"]
    else:
        return None, None
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "key": row.get("key") or row.get("testCaseKey"),
                "name": row.get("name") or "",
                "labels": row.get("labels") or [],
                "objective": row.get("objective"),
                "precondition": row.get("precondition"),
            }
        )
    return items, total


def folder_query(project_key: str, folder_ids: list[str]) -> str:
    parts: list[str] = []
    for folder_id in folder_ids:
        text = str(folder_id).strip()
        if text.isdigit():
            parts.append(text)
        else:
            parts.append('"' + text.replace('"', '\\"') + '"')
    return f'projectKey = "{project_key}" AND folder IN ({", ".join(parts)})'


def expand_folder_scope(tree: Any, folder_ids: list[str], *, include_subfolders: bool) -> list[str]:
    selected = [str(folder_id).strip() for folder_id in folder_ids if str(folder_id).strip()]
    if not include_subfolders:
        return selected
    children_by_id: dict[str, list[str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        node_id = node.get("id", node.get("folderId"))
        raw_children = node.get("children") or node.get("folders") or node.get("childFolders") or []
        children = raw_children if isinstance(raw_children, list) else []
        if node_id is not None:
            child_ids: list[str] = []
            for child in children:
                if isinstance(child, dict) and child.get("id", child.get("folderId")) is not None:
                    child_ids.append(str(child.get("id", child.get("folderId"))))
            children_by_id[str(node_id)] = child_ids
        for child in children:
            walk(child)

    walk(tree)
    ordered: list[str] = []
    seen: set[str] = set()

    def add(folder_id: str) -> None:
        if folder_id in seen:
            return
        seen.add(folder_id)
        ordered.append(folder_id)
        for child_id in children_by_id.get(folder_id, []):
            add(child_id)

    for folder_id in selected:
        add(folder_id)
    return ordered


def sync_folder_index(
    search: Callable[[str, int, int], dict[str, Any]],
    *,
    query: str,
    page_size: int = 50,
    max_pages: int = 40,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    start = 0
    for _ in range(max_pages):
        response = search(query, page_size, start)
        if response.get("ok") is not True:
            return {
                "ok": False,
                "search_status": "api_error",
                "complete": False,
                "items": items,
                "error": response.get("error") or response.get("data"),
            }
        rows, total = extract_search_page(response)
        if rows is None:
            return {
                "ok": False,
                "search_status": "api_error",
                "complete": False,
                "items": items,
                "error": "Неизвестная схема ответа поиска. Это не пустой индекс.",
            }
        items.extend(rows)
        start += len(rows)
        if total is not None and start >= total:
            return {"ok": True, "search_status": "ok", "complete": True, "items": items, "total": total}
        if total is not None and start < total and len(rows) < page_size:
            return {
                "ok": False,
                "search_status": "index_incomplete",
                "complete": False,
                "items": items,
                "total": total,
                "error": "Число элементов не сходится с total. Индекс неполный.",
            }
        if not rows or len(rows) < page_size:
            return {"ok": True, "search_status": "ok", "complete": True, "items": items, "total": total}
    return {
        "ok": True,
        "search_status": "index_incomplete",
        "complete": False,
        "items": items,
        "note": "Загружены не все страницы. Отрицательный результат поиска дублей по этому индексу недействителен.",
    }
