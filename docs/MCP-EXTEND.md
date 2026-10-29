# Расширение MCP `user-zephyr-scale` (MVP)

Исходники MCP — каталог [`plugins/tgs-qa-cursor/zephyr-scale-mcp/`](../plugins/tgs-qa-cursor/zephyr-scale-mcp/); Cursor запускает их из `plugins/tgs-qa-cursor/mcp.json`. Для E2E по [ACCEPTANCE-E2E.md](ACCEPTANCE-E2E.md) в том же MCP нужны tools.

Ответственность и границы гарантии — [REQUIREMENTS.md](REQUIREMENTS.md) §2.1.
Способ поиска по якорям, страницы вложенных папок и `id` шагов при update здесь **не** задаются (ревью п. 1).

| Tool | Назначение | Статус |
| --- | --- | --- |
| `set_credentials`, `get_config` | Jira/Zephyr + `wiki_bearer_token` для Confluence | Есть |
| `get_confluence_page` | Materials | Есть |
| `get_jira_issue` | Materials (ключ задачи) | **Добавить** |
| `get_folder_tree`, `get_folder` | browse/select | Есть |
| `list_folder_test_cases` | sync-index без search по всему проекту | **Добавить** |
| `search_test_cases`, `get_test_case` | sync-index, dedupe, refresh | Есть |
| `create_test_case`, `update_test_case` | apply (прямые вызовы gated; запись через `apply_plan`) | Есть |
| `prepare_apply`, `apply_plan`, `resume_apply`, `sync_testcase_index`, `match_test_case_candidates` | apply, dedupe, index | Есть |
| `list_project_metadata` | status/priority при create | **Добавить** |

Перед шагом агент проверяет, что tool из колонки есть в сессии. Нет tool — stop и имя в чат. Номера версии MCP нет.

Мутации вызываются только из `/qa-apply-zephyr` после «да, применить». MCP в этом репозитории не проверяет фразу чата: агент может передать аргументы сам. Защита человека — карточка одобрения Cursor, если auto-run выключен.

## Ошибки

Ответ с ошибкой: код и короткое `message`. Без значения токена, заголовка `Authorization` и сырого тела, если в нём секрет. Агент пишет в apply-log только это.

| Ситуация | Как трактовать |
| --- | --- |
| 401, 403 | Остановить пачку |
| 429 | Один повтор после `Retry-After` (иначе пауза не длиннее 60 с). Второй раз — остановить пачку |
| 4xx по данным пункта | `failed`, пачку продолжать |
| Таймаут, обрыв, 5xx, пустой ответ | `unknown`, create не повторять |

## Контракт (минимум)

### `get_jira_issue`

- Input: `issue_key` (e.g. `PROJ-123`).
- Output: `key`, `summary`, `description` (plain/markdown), optional `components[]`, `labels[]`.

### `list_folder_test_cases`

- Input: `project_key`, `folder_id`, pagination (`startAt`, `maxResults` ≤ разумного, e.g. 50).
- Output: список summary полей как в [schemas/zephyr-index.example.json](../plugins/tgs-qa-cursor/schemas/zephyr-index.example.json) — **без** полного testScript.
- Полнота обхода страниц и вложенных папок — открытый вопрос ревью п. 1. Пока выгрузка не закончена или агент не уверен, index помечается `"complete": false`.

### `update_test_case`

- Input: `key` и только те поля, которые есть в diff preview (name, steps, folder, status, priority — по решению apply).
- Output: updated `key` или error.
- Неизменённые шаги клиент не присылает. Замена шагов — только после фразы QA «заменить шаги». Сопоставление `id` шагов не входит в этот контракт.

### `list_project_metadata`

- Input: `project_key`.
- Output: допустимые `statuses[]`, `priorities[]`, optional `folders` hint.

Сводка пробелов: [MCP-GAP-ANALYSIS.md](MCP-GAP-ANALYSIS.md).
