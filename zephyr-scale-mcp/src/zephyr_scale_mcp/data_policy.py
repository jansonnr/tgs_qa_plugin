from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

MAX_AGENT_STRING = 4000

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
            r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+\Z"
        ),
    ),
    (
        "bearer",
        re.compile(
            r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}(?![A-Za-z0-9._~+/=-])"
        ),
    ),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "assigned_secret",
        re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b\s*[:=]\s*\S{12,}"),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)

_TEXT_FIELDS = ("name", "objective", "precondition", "folder")
_STEP_FIELDS = ("description", "step", "expectedResult", "expected_result", "testData", "test_data")

LOCAL_STORAGE = (
    "Артефакты прогона хранятся только локально у пользователя. "
    "Git для этого не нужен и не используется."
)
DIRECT_HTTP_BOUNDARY = (
    "Гарантия apply_token действует только для вызовов MCP. "
    "Прямой HTTP из терминала с PAT пользователя обходит MCP."
)


class QaPathError(ValueError):
    """Путь артефакта выходит за каталог .qa."""


def finding_id(kind: str, secret: str) -> str:
    return hashlib.sha256(f"{kind}:{secret}".encode()).hexdigest()[:12]


def scan_text(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            identifier = finding_id(kind, match.group(0))
            if identifier in seen:
                continue
            seen.add(identifier)
            found.append({"id": identifier, "kind": kind})
    return found


def mask_secrets(text: str) -> tuple[str, int]:
    masked = text
    count = 0
    for _kind, pattern in _PATTERNS:
        masked, replaced = pattern.subn("[secret]", masked)
        count += replaced
    return masked, count


def page_text(text: str, *, offset: int = 0, limit: int = MAX_AGENT_STRING) -> dict[str, Any]:
    """Порция текста для агента. complete=false значит, что хвост ещё не прочитан."""
    masked, masked_count = mask_secrets(text)
    start = max(0, offset)
    complete = start >= len(masked)
    if complete:
        shown = ""
        next_offset = len(masked)
    elif len(masked) - start > limit:
        shown = masked[start : start + limit - 1] + "…"
        next_offset = start + limit - 1
        complete = False
    else:
        shown = masked[start:]
        next_offset = len(masked)
        complete = True
    return {
        "text": shown,
        "next_offset": next_offset,
        "complete": complete,
        "secrets_masked": masked_count,
        "original_chars": len(text),
    }


def sanitize_text(text: str, *, limit: int = 300) -> str:
    masked, _count = mask_secrets(text.replace("\n", " "))
    if len(masked) <= limit:
        return masked
    return masked[: limit - 1] + "…"


def scan_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for _path, text in _plan_texts(plan):
        for item in scan_text(text):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            found.append(item)
    return found


def enforce_secret_decisions(plan: dict[str, Any]) -> None:
    from zephyr_scale_mcp.plan_rules import PlanRejected

    findings = scan_plan(plan)
    decisions = plan.get("secret_decisions") if isinstance(plan.get("secret_decisions"), dict) else {}
    unresolved = [item for item in findings if decisions.get(item["id"]) not in {"confirm", "exclude"}]
    if not unresolved:
        return
    summary = ", ".join(f"{item['kind']}:{item['id']}" for item in unresolved)
    raise PlanRejected(
        "SECRETS_UNRESOLVED",
        "В плане есть секреты (" + summary + "). "
        "Для каждого id укажи secret_decisions: confirm или exclude. exclude заменяет секрет на [secret] перед записью.",
    )


def redact_operations(plan: dict[str, Any]) -> list[dict[str, Any]]:
    operations = plan.get("operations") or []
    decisions = plan.get("secret_decisions") if isinstance(plan.get("secret_decisions"), dict) else {}
    excluded = {item["id"] for item in scan_plan(plan) if decisions.get(item["id"]) == "exclude"}
    if not excluded:
        return operations
    redacted: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            redacted.append(operation)
            continue
        copy = dict(operation)
        for field in _TEXT_FIELDS:
            if isinstance(copy.get(field), str):
                copy[field] = _redact_value(copy[field], excluded)
        steps = copy.get("steps")
        if isinstance(steps, list):
            copy["steps"] = [_redact_step(step, excluded) for step in steps]
        redacted.append(copy)
    return redacted


def resolve_attachment_path(file_path: str) -> Path:
    """Локальный файл для upload — только внутри каталога .qa (защита от произвольного чтения)."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise QaPathError(f"Файл не найден: {path}")
    qa_root: Path | None = None
    for parent in path.parents:
        if parent.name == ".qa":
            qa_root = parent
            break
    if qa_root is None:
        raise QaPathError("Вложение можно загружать только из файла внутри каталога .qa.")
    try:
        path.relative_to(qa_root)
    except ValueError as exc:
        raise QaPathError("Путь вложения выходит за каталог .qa.") from exc
    return path


def resolve_qa_log_dir(qa_root: str) -> Path:
    root = Path(qa_root).expanduser().resolve()
    if root.name != ".qa":
        raise QaPathError("qa_root должен быть каталогом с именем .qa.")
    log_dir = (root / "apply-logs").resolve()
    if root not in log_dir.parents:
        raise QaPathError("Журнал можно записать только внутри .qa.")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def to_agent(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is False and "results" not in payload:
        return _public_error(payload)
    cleaned, stats = _walk(payload)
    if isinstance(cleaned, dict):
        cleaned.pop("url", None)
        cleaned["context"] = stats
        return cleaned
    return {"ok": True, "context": stats, "data": cleaned}


def _public_error(payload: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {
        "ok": False,
        "error": sanitize_text(str(payload.get("error") or "Запрос не выполнен.")),
    }
    if payload.get("code"):
        public["code"] = payload["code"]
    if payload.get("status_code") is not None:
        public["status_code"] = payload["status_code"]
    if payload.get("retry_after") is not None:
        public["retry_after"] = payload["retry_after"]
    return public


def _walk(value: Any) -> tuple[Any, dict[str, int]]:
    empty = {"original_chars": 0, "returned_chars": 0, "truncated": 0, "secrets_masked": 0}
    if isinstance(value, dict) and value.get("ok") is False and "status_code" in value:
        return _public_error(value), empty
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        stats = dict(empty)
        for key, item in value.items():
            if key in {"url", "context"}:
                continue
            converted, item_stats = _walk(item)
            cleaned[key] = converted
            _add_stats(stats, item_stats)
        return cleaned, stats
    if isinstance(value, list):
        cleaned_list = []
        stats = dict(empty)
        for item in value:
            converted, item_stats = _walk(item)
            cleaned_list.append(converted)
            _add_stats(stats, item_stats)
        return cleaned_list, stats
    if isinstance(value, str):
        masked, masked_count = mask_secrets(value)
        original = len(value)
        truncated = 1 if len(masked) > MAX_AGENT_STRING else 0
        if truncated:
            shown = masked[: MAX_AGENT_STRING - 1] + "…"
        else:
            shown = masked
        return shown, {
            "original_chars": original,
            "returned_chars": len(shown),
            "truncated": truncated,
            "secrets_masked": masked_count,
        }
    return value, empty


def _add_stats(total: dict[str, int], item: dict[str, int]) -> None:
    for key in total:
        total[key] += item[key]


def _plan_texts(plan: dict[str, Any]) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    operations = plan.get("operations")
    if not isinstance(operations, list):
        return texts
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            continue
        for field in _TEXT_FIELDS:
            value = operation.get(field)
            if isinstance(value, str) and value:
                texts.append((f"operations[{index}].{field}", value))
        steps = operation.get("steps")
        if not isinstance(steps, list):
            continue
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            for field in _STEP_FIELDS:
                value = step.get(field)
                if isinstance(value, str) and value:
                    texts.append((f"operations[{index}].steps[{step_index}].{field}", value))
    return texts


def _redact_value(text: str, excluded: set[str]) -> str:
    redacted = text
    for kind, pattern in _PATTERNS:
        def replace(match: re.Match[str], secret_kind: str = kind) -> str:
            if finding_id(secret_kind, match.group(0)) in excluded:
                return "[secret]"
            return match.group(0)

        redacted = pattern.sub(replace, redacted)
    return redacted


def _redact_step(step: Any, excluded: set[str]) -> Any:
    if not isinstance(step, dict):
        return step
    copy = dict(step)
    for field in _STEP_FIELDS:
        if isinstance(copy.get(field), str):
            copy[field] = _redact_value(copy[field], excluded)
    return copy
