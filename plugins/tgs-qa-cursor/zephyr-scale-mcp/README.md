# zephyr-scale-mcp

MCP-сервер Jira / Zephyr Scale / Confluence для плагина **tgs-qa-cursor**.

## Установка зависимостей

Команду выполняй **в этом каталоге** (здесь `pyproject.toml`), не в родительском `tgs-qa-cursor`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Проверка:

```powershell
.\.venv\Scripts\python.exe -m zephyr_scale_mcp --help
```

## Конфигурация

Токены — вручную, см. корневой [README.md](../../../README.md) (раздел «Доступ к Jira / Zephyr / Confluence»).

Файл по умолчанию (Windows): `%APPDATA%\zephyr-scale-mcp\config.json`.
