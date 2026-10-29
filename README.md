# tgs-qa-cursor

Cursor-плагин для QA: материалы, doc review, черновики тест-кейсов, dedupe и
apply (create/update) в Zephyr Scale.

Репозиторий: [jansonnr/tgs_qa_plugin](https://github.com/jansonnr/tgs_qa_plugin).
Форматы и поведение: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

Код плагина: [plugins/tgs-qa-cursor/](plugins/tgs-qa-cursor/). Team marketplace:
[.cursor-plugin/marketplace.json](.cursor-plugin/marketplace.json).

**Scope v0.3:** materials, doc review, testcases, Zephyr dedupe/apply.

## Установка плагина

1. **Team marketplace:** Dashboard → Plugins → marketplace → **Refresh** → в IDE: Customize → Plugins → **TGS QA Cursor**.
2. **Локально:** каталог `plugins/tgs-qa-cursor` → `~/.cursor/plugins/local/tgs-qa-cursor` (или symlink) → Reload Window.

Отдельно MCP в Settings добавлять **не нужно** — сервер **zephyr-scale** идёт из `plugin.json` плагина.

## Python для MCP

MCP — Python-процесс из [plugins/tgs-qa-cursor/zephyr-scale-mcp/](plugins/tgs-qa-cursor/zephyr-scale-mcp/). Зависимости на машине ставит пользователь:

```powershell
cd plugins\tgs-qa-cursor\zephyr-scale-mcp
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Если системный `python` не видит пакет — в `%USERPROFILE%\.cursor\mcp.json` укажите полный путь к
`.venv\Scripts\python.exe` и те же `cwd` / `PYTHONPATH`, что в
[plugins/tgs-qa-cursor/mcp.example.json](plugins/tgs-qa-cursor/mcp.example.json) (это замена команды запуска, не второй MCP).

## Доступ к Jira / Zephyr / Confluence (вручную)

Токены **не** настраиваются через чат и tool `set_credentials`. Только ручная конфигурация на компьютере пользователя.

**Вариант A — файл (рекомендуется на Windows):**

`%APPDATA%\zephyr-scale-mcp\config.json`

```json
{
  "base_url": "https://your-jira-host.example/soft",
  "bearer_token": "YOUR_JIRA_ZEPHYR_PAT",
  "wiki_bearer_token": "YOUR_CONFLUENCE_PAT",
  "project_key": "QA",
  "project_id": "10104",
  "wiki_url": ""
}
```

`wiki_url` можно оставить пустым — тогда wiki = `{base_url}/wiki`. Файл не коммитить.

**Вариант B — переменные окружения** (имеют приоритет над файлом):

| Переменная | Назначение |
| --- | --- |
| `ZEPHYR_BEARER_TOKEN` | Jira / Zephyr API |
| `ZEPHYR_WIKI_BEARER_TOKEN` | Confluence |
| `ZEPHYR_BASE_URL` | Базовый URL (без `/wiki`) |
| `ZEPHYR_WIKI_URL` | Confluence, если не `{base_url}/wiki` |
| `ZEPHYR_PROJECT_KEY` / `ZEPHYR_PROJECT_ID` | Дефолты проекта |

Их можно прописать в `env` блока `zephyr-scale` в `%USERPROFILE%\.cursor\mcp.json`, если переопределяете команду Python.

После правок — Reload Window или перезапуск MCP в Cursor.

## Рабочий проект

В `.gitignore` репозитория, где ведёте QA:

```gitignore
.qa/cache/
```

Первый сценарий: `/qa-materials` → `/qa-testcases` → **`/qa-anchors`** → `/qa-zephyr-select` → `/qa-zephyr-sync-index` → `/qa-dedupe` → preview → «да, применить» → `/qa-apply-zephyr`.

## Команды

| Этап | Slash |
| --- | --- |
| Справка | `/qa-help` |
| Материалы → кейсы | `/qa-materials`, `/qa-doc-review`, `/qa-testcases` |
| Якоря dedupe | `/qa-anchors` |
| Zephyr | `/qa-zephyr-browse`, `/qa-zephyr-select`, `/qa-zephyr-sync-index`, `/qa-zephyr-refresh`, `/qa-dedupe`, `/qa-apply-zephyr` |

Промпты: [plugins/tgs-qa-cursor/prompts/](plugins/tgs-qa-cursor/prompts/). Примеры JSON: [plugins/tgs-qa-cursor/schemas/](plugins/tgs-qa-cursor/schemas/). Контракт MCP: [docs/MCP-EXTEND.md](docs/MCP-EXTEND.md).

При create в Zephyr метка **`AI_Cursor`** — [plugins/tgs-qa-cursor/config/zephyr-defaults.yaml](plugins/tgs-qa-cursor/config/zephyr-defaults.yaml).

## Лицензия

[MIT](LICENSE). Copyright (c) 2026 Nelli.

## Версия

0.3.6 — [CHANGELOG.md](CHANGELOG.md).
