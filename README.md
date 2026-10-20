# tgs-qa-cursor

Cursor-плагин для QA: материалы, doc review, черновики тест-кейсов, dedupe и
apply (create/update) в Zephyr Scale через MCP.

Отдельный проект. [Test Generator Suite](https://github.com/bezobrazieq/tgs) —
источник идей; форматы и поведение задаёт [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Требования

Канон: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), решения —
[docs/MVP-DECISIONS.md](docs/MVP-DECISIONS.md).

**Scope v0.3:** materials, doc review, testcases, Zephyr dedupe/apply. Без case review,
API-тестов, базы знаний и test run.

## Промпты

Редактируемые шаблоны для модели: [prompts/README.md](prompts/README.md). Skills
подключают их при `/qa-materials`, doc review, testcases, dedupe и apply.

## Установка (локально)

1. Склонируйте репозиторий или скопируйте каталог в
   `~/.cursor/plugins/local/tgs-qa-cursor`.
2. В Cursor: **Customize** → skills, rules, commands.
3. MCP: `user-zephyr-scale` — [mcp.example.json](mcp.example.json),
   пробелы API — [docs/MCP-GAP-ANALYSIS.md](docs/MCP-GAP-ANALYSIS.md).
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

## Версия

0.3.3 — см. [CHANGELOG.md](CHANGELOG.md).
