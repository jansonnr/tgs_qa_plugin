# tgs-qa-cursor

Cursor-плагин для QA: материалы, doc review, черновики тест-кейсов, dedupe и
apply (create/update) в Zephyr Scale через MCP.

Репозиторий: [jansonnr/tgs_qa_plugin](https://github.com/jansonnr/tgs_qa_plugin).
[Test Generator Suite](https://github.com/bezobrazieq/tgs) — источник идей;
форматы и поведение задаёт [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

Код плагина: [plugins/tgs-qa-cursor/](plugins/tgs-qa-cursor/). Team marketplace:
[.cursor-plugin/marketplace.json](.cursor-plugin/marketplace.json).

## Требования

Канон: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), решения —
[docs/MVP-DECISIONS.md](docs/MVP-DECISIONS.md).

**Scope v0.3:** materials, doc review, testcases, Zephyr dedupe/apply. Без case review,
API-тестов, базы знаний и test run.

## Промпты

Редактируемые шаблоны для модели: [plugins/tgs-qa-cursor/prompts/README.md](plugins/tgs-qa-cursor/prompts/README.md). Skills
подключают их при `/qa-materials`, doc review, testcases, dedupe и apply.

## Установка

1. **Team marketplace (Teams):** Dashboard → Plugins → ваш marketplace → **Refresh** после push в GitHub. В IDE: Customize → Plugins → установить **tgs-qa-cursor**.
2. **Локально:** клон репозитория, затем каталог `plugins/tgs-qa-cursor` в
   `~/.cursor/plugins/local/tgs-qa-cursor` (или symlink) → Reload Window.
3. Плагин поднимает MCP **zephyr-scale** из [plugins/tgs-qa-cursor/mcp.json](plugins/tgs-qa-cursor/mcp.json) (код в
   [plugins/tgs-qa-cursor/zephyr-scale-mcp/](plugins/tgs-qa-cursor/zephyr-scale-mcp/)). Нужен Python 3.11+ и зависимости:

   ```powershell
   cd plugins\tgs-qa-cursor\zephyr-scale-mcp
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e .
   ```

   Cursor должен вызывать тот же Python (или укажите полный путь к
   `.venv\Scripts\python.exe` в своём `%USERPROFILE%\.cursor\mcp.json`, если
   дублируете сервер вручную). Токены — один раз `set_credentials` (см.
   [docs/MCP-EXTEND.md](docs/MCP-EXTEND.md)).
4. Пробелы API для materials/index: [docs/MCP-GAP-ANALYSIS.md](docs/MCP-GAP-ANALYSIS.md).
5. В рабочем проекте QA добавьте в `.gitignore`:

   ```gitignore
   .qa/cache/
   ```

6. Первый запуск: `/qa-materials` → … → `/qa-testcases` → **`/qa-anchors`** → dedupe в Zephyr.

## Команды

| Этап | Slash |
| --- | --- |
| Справка | `/qa-help` |
| Материалы → кейсы | `/qa-materials`, `/qa-doc-review`, `/qa-testcases` |
| Якоря dedupe | `/qa-anchors` |
| Zephyr | `/qa-zephyr-browse`, `/qa-zephyr-select`, `/qa-zephyr-sync-index`, `/qa-zephyr-refresh`, `/qa-dedupe`, `/qa-apply-zephyr` |

Примеры JSON: [plugins/tgs-qa-cursor/schemas/](plugins/tgs-qa-cursor/schemas/). MCP: [docs/MCP-EXTEND.md](docs/MCP-EXTEND.md).

Импорт в Zephyr: метка **`AI_Cursor`** на create — [plugins/tgs-qa-cursor/config/zephyr-defaults.yaml](plugins/tgs-qa-cursor/config/zephyr-defaults.yaml) (MCP подставляет при apply).

## Лицензия

[MIT](LICENSE). Copyright (c) 2026 Nelli.

## Версия

0.3.6 — см. [CHANGELOG.md](CHANGELOG.md).
