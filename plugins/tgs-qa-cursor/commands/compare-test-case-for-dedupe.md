---
name: compare-test-case-for-dedupe
description: Сравнить черновик с кейсами Zephyr и собрать dedupe-plan
---

Run skill **`qa-dedupe`** for the current or given `run-id` draft under `.qa/drafts/testcases/`.

Preconditions:

- `search_anchors_confirmed: true` и `anchors_draft_revision` совпадает с черновиком; иначе stop → `/key-words`.
- Непустые `select_folders` и `project_key`; иначе stop → `/select-folders`.
- Index: `/search-by-keyword` или существующий `.qa/cache/zephyr/.../index.json`. Ошибка или `complete: false` не дают `create`.

Не вызывай create/update MCP в этом шаге.

Следующий шаг: preview плана → «да, применить» → `/import-in-zephyr`.
