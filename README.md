# TGS QA Cursor

Cursor-плагин для QA: материалы, doc review, черновики кейсов, dedupe и import в Zephyr Scale.

Репозиторий: [jansonnr/tgs_qa_plugin](https://github.com/jansonnr/tgs_qa_plugin).  
Требования к поведению: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

---

## Что нужно на ПК

- **Git**
- **Cursor**
- **Python 3.11+** или [**uv**](https://docs.astral.sh/uv/) (для Jira/Zephyr из плагина; отдельный MCP в Settings не добавляют)

---

## Установка

### 1. Clone

```powershell
git clone https://github.com/jansonnr/tgs_qa_plugin.git C:\tools\tgs_qa_plugin
cd C:\tools\tgs_qa_plugin
```

### 2. Скрипт (копия плагина + Python)

```powershell
.\scripts\install-tgs-qa-cursor.ps1 -UseThisRepo -WriteConfigTemplate
```

Скрипт кладёт плагин сюда:

`%USERPROFILE%\.cursor\plugins\local\tgs-qa-cursor`

и ставит зависимости в `...\local\tgs-qa-cursor\zephyr-scale-mcp`. **Junction/symlink не используются** — Cursor так видит local-плагины.

Повторная установка / обновление после `git pull`:

```powershell
.\scripts\install-tgs-qa-cursor.ps1 -UseThisRepo -Force
```

### 3. Cursor

1. **Reload Window**
2. **Customize → Plugins** → включить **TGS QA Cursor**
3. Если плагина нет — включить **Include third-party Plugins, Skills, and other configs**; на Teams/Enterprise админ должен разрешить **Allow Local Plugin Imports**

### 4. Токены (вручную)

Файл `%APPDATA%\zephyr-scale-mcp\config.json`:

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

Не коммитить. `-WriteConfigTemplate` создаёт файл **только если его ещё нет**.

### 5. Проверка

Откройте **репозиторий продукта** (не `tgs_qa_plugin`) → в чате `/qa-help`.

---

## Рабочий проект (отдельный git)

В репозитории, где ведёте задачу, в `.gitignore`:

```gitignore
.qa/cache/
```

В clone плагина (`C:\tools\tgs_qa_plugin`) это **не обязательно**.

---

## Если Zephyr/Jira не отвечают

**`ModuleNotFoundError: No module named 'mcp'`** — зависимости стоят в venv плагина, а Cursor вызвал другой Python. В `mcp.json` плагина сервер запускается через [run_mcp.py](plugins/tgs-qa-cursor/zephyr-scale-mcp/run_mcp.py): system `python` только стартует скрипт, MCP идёт из `.venv` в local-копии.

1. Убедитесь, что venv есть:  
   `%USERPROFILE%\.cursor\plugins\local\tgs-qa-cursor\zephyr-scale-mcp\.venv\`
2. Если нет или ошибка остаётся после **Reload Window**:

   ```powershell
   cd C:\tools\tgs_qa_plugin
   .\scripts\install-tgs-qa-cursor.ps1 -UseThisRepo -Force
   ```

3. Ручное переопределение (редко нужно): в `%USERPROFILE%\.cursor\mcp.json` укажите `.venv\Scripts\python.exe` — см. [mcp.example.json](plugins/tgs-qa-cursor/mcp.example.json).

Другие сбои tools (401, timeout) — проверьте `%APPDATA%\zephyr-scale-mcp\config.json`.

---

## Команды

| Этап | Slash |
| --- | --- |
| Справка | `/qa-help` |
| Материалы → кейсы | `/get-confluence-page`, `/review-user-story`, `/create-test-case` |
| Ключевые слова | `/key-words` |
| Zephyr | `/search-test-case-in-zephyr`, `/select-folders`, `/search-by-keyword`, `/update-test-case`, `/compare-test-case-for-dedupe`, `/import-in-zephyr` |

Промпты: [plugins/tgs-qa-cursor/prompts/](plugins/tgs-qa-cursor/prompts/).  
MCP tools: [docs/MCP-EXTEND.md](docs/MCP-EXTEND.md).  
Метка create в Zephyr: **`AI_Cursor`** — [config/zephyr-defaults.yaml](plugins/tgs-qa-cursor/config/zephyr-defaults.yaml).

---

## Team marketplace (опционально)

Dashboard → import repo → Refresh. Для разработки команды проще **clone + скрипт** выше: путь стабильный, без `marketplaces\...\<commit>\`.

---

## Лицензия

[MIT](LICENSE). Версия: [CHANGELOG.md](CHANGELOG.md).
