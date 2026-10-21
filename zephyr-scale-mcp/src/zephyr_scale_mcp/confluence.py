from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup, NavigableString, PageElement, Tag

from zephyr_scale_mcp.config import ConfigError, Settings, get_settings


class ConfluenceClientError(RuntimeError):
    """Ошибка при работе с Confluence."""


@dataclass
class ConfluencePage:
    page_id: str
    title: str
    body_html: str


def extract_page_id(value: str) -> str | None:
    candidate = value.strip()
    if candidate.isdecimal():
        return candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    values = parse_qs(parsed.query).get("pageId")
    if not values:
        return None
    page_id = values[0].strip()
    return page_id if page_id.isdecimal() else None


class ConfluenceClient:
    """Минимальный read-only клиент Confluence REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._base_url = self.settings.wiki_url_resolved()
        self._http = httpx.Client(timeout=60.0, follow_redirects=True)

    def fetch_page(self, page_id: str) -> ConfluencePage:
        data = self._http_get(
            f"{self._base_url}/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        body = (data.get("body", {}).get("storage", {}) or {}).get("value", "")
        return ConfluencePage(page_id=page_id, title=data.get("title", ""), body_html=body)

    def page_to_text(self, page: ConfluencePage, *, max_depth: int = 0) -> str:
        text = html_to_markdown(page.body_html)
        if max_depth > 0:
            for linked in extract_linked_page_ids(page.body_html, lookup=self._lookup_page_id_by_title):
                if linked == page.page_id:
                    continue
                try:
                    sub = self.fetch_page(linked)
                except ConfluenceClientError:
                    continue
                text += f"\n\n--- Связанная страница: {sub.title} ---\n"
                text += html_to_markdown(sub.body_html)
        return text

    def get_page(self, page_id_or_url: str, *, max_depth: int = 0) -> dict[str, Any]:
        page_id = extract_page_id(page_id_or_url)
        if not page_id:
            raise ConfluenceClientError(
                "Укажи числовой pageId или URL Confluence с параметром pageId=..."
            )
        page = self.fetch_page(page_id)
        return {
            "ok": True,
            "page_id": page.page_id,
            "title": page.title,
            "content_markdown": self.page_to_text(page, max_depth=max_depth),
            "url": f"{self._base_url}/pages/viewpage.action?pageId={page.page_id}",
        }

    def _lookup_page_id_by_title(self, title: str) -> str | None:
        escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
        try:
            results = self._http_get(
                f"{self._base_url}/rest/api/search",
                params={"cql": f'type=page AND title="{escaped_title}"', "limit": 1},
            )
        except ConfluenceClientError:
            return None
        items = results.get("results") or []
        if not items:
            return None
        content = items[0].get("content") or {}
        page_id = content.get("id")
        return str(page_id) if page_id is not None else None

    def _http_get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._http.get(url, headers=self._auth_headers(), params=params)
        except httpx.HTTPError as exc:
            raise ConfluenceClientError("Не удалось загрузить страницу Confluence") from exc

        if response.status_code != 200:
            raise ConfluenceClientError(
                f"Confluence вернул {response.status_code} при загрузке страницы"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConfluenceClientError("Confluence вернул нечитаемый ответ") from exc
        if not isinstance(payload, dict):
            raise ConfluenceClientError("Confluence вернул неожиданный формат ответа")
        return payload

    def _auth_headers(self) -> dict[str, str]:
        try:
            return {
                "Authorization": self.settings.wiki_auth_header(),
                "Accept": "application/json",
            }
        except ConfigError as exc:
            raise ConfluenceClientError(str(exc)) from exc


def extract_linked_page_ids(
    html_or_text: str,
    *,
    lookup: Callable[[str], str | None] | None = None,
) -> Iterator[str]:
    seen: set[str] = set()
    for match in re.finditer(r"pageId=(\d+)", html_or_text):
        page_id = match.group(1)
        if page_id not in seen:
            seen.add(page_id)
            yield page_id

    soup = BeautifulSoup(html_or_text, "lxml")
    for tag in soup.find_all("ri:page"):
        title = attribute_text(tag, "ri:content-title")
        if not title or lookup is None:
            continue
        page_id = lookup(title)
        if page_id and page_id not in seen:
            seen.add(page_id)
            yield page_id


def html_to_markdown(html_text: str) -> str:
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "lxml")
    return node_to_markdown(soup).strip()


def node_to_markdown(node: PageElement) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""

    tag_name = node.name.lower() if node.name else ""

    if tag_name in {"script", "style"}:
        return ""

    if tag_name in {"br"}:
        return "\n"

    if tag_name in {"p", "div"}:
        inner = "".join(node_to_markdown(child) for child in node.children)
        return inner.strip() + "\n\n"

    if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag_name[1])
        inner = "".join(node_to_markdown(child) for child in node.children).strip()
        return f"\n{'#' * level} {inner}\n\n"

    if tag_name in {"strong", "b"}:
        return f"**{''.join(node_to_markdown(child) for child in node.children)}**"

    if tag_name in {"em", "i"}:
        return f"*{''.join(node_to_markdown(child) for child in node.children)}*"

    if tag_name == "code":
        return f"`{''.join(node_to_markdown(child) for child in node.children)}`"

    if tag_name == "pre":
        text = node.get_text()
        return f"\n```\n{text.rstrip()}\n```\n"

    if tag_name == "a":
        href = attribute_text(node, "href")
        inner = "".join(node_to_markdown(child) for child in node.children).strip()
        if not inner:
            inner = href
        return f"[{inner}]({href})" if href else inner

    if tag_name in {"ul", "ol"}:
        return list_to_markdown(node, ordered=tag_name == "ol")

    if tag_name == "table":
        return table_to_markdown(node)

    return "".join(node_to_markdown(child) for child in node.children)


def attribute_text(node: Tag, name: str) -> str:
    value = node.get(name)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return " ".join(str(item) for item in value)


def list_to_markdown(list_node: Tag, *, ordered: bool) -> str:
    parts: list[str] = []
    for i, li in enumerate(list_node.find_all("li", recursive=False), start=1):
        bullet = f"{i}." if ordered else "-"
        inner = "".join(node_to_markdown(child) for child in li.children).strip()
        parts.append(f"{bullet} {inner}")
    return "\n" + "\n".join(parts) + "\n"


def table_to_markdown(table_node: Tag) -> str:
    rows = table_node.find_all("tr")
    if not rows:
        return ""
    lines: list[str] = []
    for idx, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        rendered_cells = [
            re.sub(r"\s+", " ", node_to_markdown(cell)).strip() or " " for cell in cells
        ]
        lines.append("| " + " | ".join(rendered_cells) + " |")
        if idx == 0:
            lines.append("|" + "|".join("---" for _ in rendered_cells) + "|")
    return "\n" + "\n".join(lines) + "\n"
