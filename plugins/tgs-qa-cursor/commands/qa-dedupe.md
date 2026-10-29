---
name: qa-dedupe
description: Сопоставление черновика с index Zephyr и dedupe-plan.json
---

Run skill **`qa-dedupe`** for the current or given `run-id` draft under `.qa/drafts/testcases/`.

Preconditions:

- `search_anchors_confirmed: true` и `anchors_draft_revision` совпадает с черновиком; иначе stop → `/qa-anchors`.
- Непустые `search_folders` и `project_key`; иначе stop → `/qa-zephyr-select`.
- Index: `/qa-zephyr-sync-index` или существующий `.qa/cache/zephyr/.../index.json`. Ошибка или `complete: false` не дают `create`.

Не вызывай create/update MCP в этом шаге.
