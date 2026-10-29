"""Ключи Zephyr до попадания в путь HTTP-запроса."""

from __future__ import annotations

import re
from urllib.parse import quote

_CASE_KEY = re.compile(r"^[A-Z][A-Z0-9]+-T\d+$")
_RUN_KEY = re.compile(r"^[A-Z][A-Z0-9]+-R\d+$")
_NUMERIC_ID = re.compile(r"^[1-9]\d*$|^0$")
_ALLOWED_PREFIXES = ("/rest/atm/1.0/", "/rest/tests/1.0/")


class UnsafeKey(ValueError):
    """Ключ или id нельзя подставлять в путь API."""


def require_case_key(value: object) -> str:
    return _require(value, _CASE_KEY, "ключ тест-кейса")


def require_run_key(value: object) -> str:
    return _require(value, _RUN_KEY, "ключ тест-рана")


def require_numeric_id(value: object, *, what: str) -> str:
    return _require(value, _NUMERIC_ID, what)


def path_segment(value: str) -> str:
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise UnsafeKey("В сегменте пути нельзя использовать разделители и dot-сегменты.")
    return quote(value, safe="")


def assert_api_path(path: str) -> None:
    segments = [segment for segment in path.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        raise UnsafeKey("Итоговый путь выходит за API Zephyr.")
    if not any(path.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise UnsafeKey("Итоговый путь выходит за API Zephyr.")


def _require(value: object, pattern: re.Pattern[str], what: str) -> str:
    text = str(value or "").strip()
    if any(mark in text for mark in ("/", "\\", "?", "#", "..")) or not pattern.fullmatch(text):
        raise UnsafeKey(f"Недопустимый {what}.")
    return text
