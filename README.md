# tgs-qa-cursor

Cursor-плагин для QA: материалы, doc review, черновики тест-кейсов, dedupe и
apply (create/update) в Zephyr Scale через MCP.

Репозиторий: [jansonnr/tgs_qa_plugin](https://github.com/jansonnr/tgs_qa_plugin).
[Test Generator Suite](https://github.com/bezobrazieq/tgs) — источник идей;
форматы и поведение задаёт [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Требования

Канон: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), решения —
[docs/MVP-DECISIONS.md](docs/MVP-DECISIONS.md).

**Scope v0.3:** materials, doc review, testcases, Zephyr dedupe/apply. Без case review,
API-тестов, базы знаний и test run.

## Промпты

Редактируемые шаблоны для модели: [prompts/README.md](prompts/README.md). Skills
подключают их при `/qa-materials`, doc review, testcases, dedupe и apply.

## Установка

1. **Marketplace или git:** Customize → Plugins → `tgs-qa-cursor`, либо клон в
   `~/.cursor/plugins/local/tgs-qa-cursor` и Reload Window.
2. Плагин поднимает MCP **zephyr-scale** из [mcp.json](mcp.json) (код в
   [zephyr-scale-mcp/](zephyr-scale-mcp/)). Нужен Python 3.11+ и зависимости:

   ```powershell
   cd zephyr-scale-mcp
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e .
   ```

   Cursor должен вызывать тот же Python (или укажите полный путь к
   `.venv\Scripts\python.exe` в своём `%USERPROFILE%\.cursor\mcp.json`, если
   дублируете сервер вручную). Токены — один раз `set_credentials` (см.
   [zephyr-scale-mcp/README.md](zephyr-scale-mcp/README.md)).
3. Пробелы API для materials/index: [docs/MCP-GAP-ANALYSIS.md](docs/MCP-GAP-ANALYSIS.md).
4. В рабочем проекте QA добавьте в `.gitignore`:

   ```gitignore
   .qa/cache/
   ```

5. Первый запуск: `/qa-materials` → … → `/qa-testcases` → **`/qa-anchors`** → dedupe в Zephyr.

## Команды

| Этап | Slash |
| --- | --- |
| Справка | `/qa-help` |
| Материалы → кейсы | `/qa-materials`, `/qa-doc-review`, `/qa-testcases` |
| Якоря dedupe | `/qa-anchors` |
| Zephyr | `/qa-zephyr-browse`, `/qa-zephyr-select`, `/qa-zephyr-sync-index`, `/qa-zephyr-refresh`, `/qa-dedupe`, `/qa-apply-zephyr` |

Примеры JSON: [schemas/](schemas/). MCP: [docs/MCP-EXTEND.md](docs/MCP-EXTEND.md).

## Лицензия

[MIT](LICENSE). Copyright (c) 2026 Nelli.

## Версия

0.3.5 — см. [CHANGELOG.md](CHANGELOG.md).
