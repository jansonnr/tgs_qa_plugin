---
name: review-user-story
description: Ревью user story / постановки (П1–П6)
---

Run skill **`qa-doc-review`** using `.qa/materials/manifest.json`.

Output: `.qa/reviews/doc/<run-id>.json` и `<run-id>.md`. Без RAG/KB.

Следующий шаг: `/create-test-case` (при необходимости с `--after-doc-review <run-id>`).
