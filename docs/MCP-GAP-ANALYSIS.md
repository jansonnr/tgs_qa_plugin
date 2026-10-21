# MCP gap-analysis (MVP scope)

Единая интеграция через **`user-zephyr-scale`** (расширять, не плодить отдельные MCP).

| Нужно для MVP | Tool | Статус |
| --- | --- | --- |
| Credentials, Confluence | `set_credentials`, `get_confluence_page` | Есть |
| Jira issue | `get_jira_issue` | **Добавить** |
| Browse folder | `get_folder_tree`, `get_folder` | tree есть |
| List cases in folder | `list_folder_test_cases` | **Добавить** |
| Dedupe read | `search_test_cases`, `get_test_case` | Есть; search — summary only |
| Apply | `prepare_apply`, `apply_plan`, `create_test_case`, `update_test_case` | Есть (запись через apply; прямые mutate gated) |
| Metadata | `list_project_metadata` | **Добавить** (status/priority) |

**Не нужно в MVP:** test run, last result, attachments, отдельный knowledge/RAG MCP,
отдельный `qa-parsers` MCP.

**PDF/XMind в materials:** читать через agent + `@`-file или позже один tool в
**том же** Zephyr/Atlassian MCP.

Контракт новых tools: [MCP-EXTEND.md](MCP-EXTEND.md).

Поиск по произвольным фразам, полнота вложенных папок и сохранение `id` шагов при update в этот gap **не** входят: это открытый п. 1 ревью требований. Границы согласия и прямой HTTP — [REQUIREMENTS.md](REQUIREMENTS.md) §2.1.
