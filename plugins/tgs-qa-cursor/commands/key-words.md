---
name: key-words
description: Ключевые слова для поиска по тексту тест-кейсов в Zephyr
---

Run skill **`qa-anchors`** for the current testcase draft `run-id` under `.qa/drafts/testcases/`.

- Предложи 3–10 ключевых фраз (`search_anchors`) из черновика и материалов — по ним потом ищутся похожие кейсы в TMS.
- Дождись confirm или правок пользователя.
- Запиши в manifest: `search_anchors_confirmed: true`, `anchors_draft_run_id`, `anchors_draft_revision`.

Обязательно перед `/search-by-keyword` и `/compare-test-case-for-dedupe`.
