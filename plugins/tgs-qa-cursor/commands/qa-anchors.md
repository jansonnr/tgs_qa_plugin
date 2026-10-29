---
name: qa-anchors
description: Предложение и confirm якорей dedupe после черновика testcases
---

Run skill **`qa-anchors`** for the current testcase draft `run-id` under `.qa/drafts/testcases/`.

- Предложи 3–10 `search_anchors` из черновика + материалов.
- Дождись confirm или правок пользователя.
- Запиши в manifest: `search_anchors_confirmed: true`, `anchors_draft_run_id`.

Обязательно перед `/qa-zephyr-sync-index` (search по якорям) и `/qa-dedupe`.
