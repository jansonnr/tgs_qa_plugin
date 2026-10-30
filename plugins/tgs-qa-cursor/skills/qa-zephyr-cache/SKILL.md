---
name: qa-zephyr-cache
description: Browse Zephyr folders, select TMS scope in manifest, sync index-only cache, refresh selected case bodies. Uses MCP user-zephyr-scale.
---

# Zephyr cache

Read [REQUIREMENTS.md](../../docs/REQUIREMENTS.md) §5, FR-ZEP-01…03.

## Prompts

1. [prompts/_source-trust.md](../../prompts/_source-trust.md)

## MCP (user-zephyr-scale)

| Tool | Режим |
| --- | --- |
| `get_folder_tree`, `get_folder` | browse, select |
| `list_folder_test_cases` | sync-index (когда есть в MCP) |
| `search_test_cases` | sync-index — **только** узко по якорям после confirm |
| `get_test_case` | refresh, dedupe (top candidates) |

Gap: `get_jira_issue`, `list_folder_test_cases`, `update_test_case` — см. [MCP-GAP-ANALYSIS.md](../../docs/MCP-GAP-ANALYSIS.md).

## browse

- `project_key` из manifest или от пользователя.
- `get_folder_tree` → показать дерево на русском (id, path, name).
- **Не** вызывать `search_test_cases` по якорям.
- Предложить `/qa-zephyr-select` или sync-index после `/qa-anchors`.

## select

- После browse или по известным путям: уточнить `project_key`, `search_folders[]`.
- Писать в `materials/manifest.json` только после согласия пользователя.
- **Не** выставлять `search_anchors_confirmed: true` здесь.

## sync-index

- Если `list_folder_test_cases` или `search_test_cases` нет в сессии — **stop** и назови отсутствующий tool.
- Перед **`search_test_cases` по `search_anchors`**: manifest MUST have
  `search_anchors_confirmed: true`. Иначе **stop** → `/qa-anchors`.
- `anchors_draft_run_id` и `anchors_draft_revision` MUST совпадать с черновиком; при расхождении — спросить QA.
- `search_folders` и `project_key` MUST быть заданы; иначе **stop** → `/qa-zephyr-select`.
- Набор кейсов: `list_folder_test_cases` в scope `search_folders` и/или узкий `search_test_cases` по якорям.
  Как гарантировать все страницы и вложенные папки — открытый вопрос ревью п. 1; не выдумывай полноту.
- **Не** один запрос на весь проект с огромным `maxResults`.
- `sync_testcase_index` с `include_subfolders=true` для проекта, отличного от настроенного, требует `project_id` этого же проекта. Без него MCP вернёт `index_incomplete` — это не «дублей нет».
- Если выгрузка оборвалась, вернула ошибку или полнота неясна — `"complete": false`. Иначе `"complete": true`.
- Index entry fields only: `key`, `name`, `folder`, `status`, `priority`, `updated` (без полного testScript).
- Path: `.qa/cache/zephyr/<projectKey>/folders/<folderId>/index.json`
- Update `.qa/cache/zephyr/meta.json`: `project_key`, `synced_at`, `folder_ids[]`, `complete`.

## refresh

- Input: `<run-id>.dedupe-plan.json` (или явный список ключей).
- For items with `action` ∈ `update`, `ask`: fresh `get_test_case` →
  `.qa/cache/zephyr/<projectKey>/cases/<key>.json`.
- Diff в чате строить по этому ответу, не по устаревшему файлу. Без MCP mutate.

## export-project (optional)

- Warn about size; index all folders without testScript; no background scheduler.

Never commit `.qa/cache/` to git.
