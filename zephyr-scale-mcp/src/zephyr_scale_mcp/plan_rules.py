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
    from zephyr_scale_mcp.data_policy import enforce_secret_decisions

    enforce_secret_decisions(plan)


def plan_hash(plan: dict[str, Any]) -> str:
    operations = []
    for operation in plan.get("operations") or []:
        if isinstance(operation, dict):
            operations.append({key: operation[key] for key in _HASH_FIELDS if key in operation})
    canonical = {
        "draft_revision": plan.get("draft_revision"),
        "search_status": plan.get("search_status"),
        "secret_decisions": plan.get("secret_decisions") or {},
        "operations": operations,
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def fingerprint_case(*, name: str | None, steps: list[dict[str, Any]] | None) -> str:
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
    payload = {"name": name or "", "steps": normalized}
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


def _plain(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _steps_changed(remote_steps: list[dict[str, Any]], merged: list[dict[str, Any]]) -> bool:
    if len(remote_steps) != len(merged):
        return True
    for remote_step, draft_step in zip(remote_steps, merged, strict=True):
        if remote_step.get("id") != draft_step.get("id"):
            return True
        if _step_text(remote_step) != _step_text(draft_step):
            return True
    return False


def update_changes(operation: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    data = remote.get("data") if isinstance(remote.get("data"), dict) else remote
    if not isinstance(data, dict):
        data = {}
    changes: dict[str, Any] = {}
    for field in ("name", "objective", "folder", "status", "priority"):
        if field not in operation or operation[field] is None:
            continue
        if _plain(operation[field]) != _plain(data.get(field)):
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
    return fingerprint_case(name=data.get("name"), steps=steps if isinstance(steps, list) else [])


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


def _step_score(draft_steps: list[dict[str, Any]], candidate_steps: list[dict[str, Any]]) -> float:
    if not draft_steps or not candidate_steps:
        return 0.0
    used: set[int] = set()
    total = 0.0
    for step in draft_steps:
        left = _tokens(
            f"{step.get('description') or ''} {step.get('expectedResult') or step.get('expected_result') or ''}"
        )
        best_index: int | None = None
        best = 0.0
        for index, other in enumerate(candidate_steps):
            if index in used:
                continue
            right = _tokens(
                f"{other.get('description') or ''} {other.get('expectedResult') or other.get('expected_result') or ''}"
            )
            score = _overlap(left, right)
            if score > best:
                best = score
                best_index = index
        if best_index is not None:
            used.add(best_index)
        total += best
    return total / len(draft_steps)


def match_candidates(index_items: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        phrases = [str(phrase) for phrase in (case.get("phrases") or []) if str(phrase).strip()]
        if not phrases and case.get("title"):
            phrases = [str(case["title"])]
        ranked: list[dict[str, Any]] = []
        for item in index_items:
            name_score = _phrase_score(phrases, item)
            if name_score < HIGH_NAME_SCORE:
                continue
            row: dict[str, Any] = {
                "key": item.get("key"),
                "name": item.get("name"),
                "name_score": round(name_score, 4),
            }
            if case.get("steps") and item.get("steps"):
                row["step_score"] = round(_step_score(case["steps"], item["steps"]), 4)
            ranked.append(row)
        ranked.sort(key=lambda row: (row["name_score"], row.get("step_score") or 0), reverse=True)
        shortlist = ranked[:MAX_CANDIDATES]
        if not shortlist:
            suggestion = "create"
            note = NO_MATCH_NOTE
        else:
            best = shortlist[0]
            step_score = best.get("step_score")
            if case.get("confirmed_skip") is True and step_score is not None and step_score >= SKIP_STEP_SCORE:
                suggestion = "skip"
                note = "skip только при совпадении шагов и явном confirmed_skip."
            else:
                suggestion = "ask"
                note = "Высокое совпадение по доступным полям. update или skip выбирает человек."
        results.append(
            {
                "case_id": case.get("case_id"),
                "suggested_action": suggestion,
                "note": note,
                "candidates": shortlist,
            }
        )
    return {"ok": True, "results": results}


def extract_search_page(response: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    data = response.get("data")
    rows: list[Any]
    total: int | None = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        found = data.get("results") or data.get("values") or data.get("testCases") or []
        rows = found if isinstance(found, list) else []
        if isinstance(data.get("total"), int):
            total = data["total"]
    else:
        rows = []
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
        items.extend(rows)
        if not rows:
            return {"ok": True, "search_status": "ok", "complete": True, "items": items, "total": total}
        start += len(rows)
        if total is not None and start >= total:
            return {"ok": True, "search_status": "ok", "complete": True, "items": items, "total": total}
        if len(rows) < page_size:
            return {"ok": True, "search_status": "ok", "complete": True, "items": items, "total": total}
    return {
        "ok": True,
        "search_status": "index_incomplete",
        "complete": False,
        "items": items,
        "note": "Загружены не все страницы. Отрицательный результат поиска дублей по этому индексу недействителен.",
    }
