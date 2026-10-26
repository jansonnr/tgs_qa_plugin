# Zephyr Scale MCP (часть плагина tgs-qa-cursor)

Единственный каталог исходников MCP в этом репозитории. Cursor подключает сервер через корневой [`mcp.json`](../mcp.json) и [`plugin.json`](../.cursor-plugin/plugin.json).

MCP для **Zephyr Scale Server API** (TMS в Jira): материалы Confluence, папки, индекс кейсов, dedupe, запись через `prepare_apply` / `apply_plan`.

## Зависимости

Python **3.11+**. Зависимости ставятся в тот же интерпретатор, который Cursor вызывает как `python` (см. Settings → MCP или `where python`):

```powershell
cd zephyr-scale-mcp
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Для локальной разработки можно указать в `%USERPROFILE%\.cursor\mcp.json` полный путь к `.venv\Scripts\python.exe` вместо `python`, если системный Python без пакета `mcp`.

## Токены

Токены **не** хранятся в git. После установки плагина один раз:

```text
set_credentials(
  bearer_token="...",
  wiki_bearer_token="...",
  base_url="https://track.astral.ru/soft",
  wiki_url="https://wiki.astral.ru",
  project_key="QA",
  project_id="10104"
)
```

Файл конфига: `%APPDATA%\zephyr-scale-mcp\config.json` (Windows). Переменные `ZEPHYR_*` перекрывают файл — см. исходники `config.py`.

## Запись в Zephyr

Create/update/delete только через **`prepare_apply`** и **`apply_plan`**. Прямые `create_test_case` / `update_test_case` / `delete_test_case` отклоняются (`WRITE_GATE_DENIED`), кроме отладки с `ZEPHYR_ALLOW_DIRECT_WRITE=1`.

При **create** через apply в Zephyr всегда ставится одна метка: **`AI_Cursor`** (канон: [config/zephyr-defaults.yaml](../config/zephyr-defaults.yaml)). Переопределение: env `ZEPHYR_IMPORT_LABEL`.

Контракт tools для QA-плагина и пробелы MVP: [docs/MCP-EXTEND.md](../docs/MCP-EXTEND.md).

## Тесты

```powershell
cd zephyr-scale-mcp
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
