---
name: qa-zephyr-select
description: Выбор project_key и search_folders для TMS scope в manifest
---

Run skill **`qa-zephyr-cache`** — режим **select**.

1. При необходимости сначала `/qa-zephyr-browse` для навигации по папкам.
2. Уточни у пользователя `project_key` и пути/ID папок (`search_folders`).
3. Обнови `.qa/materials/manifest.json` **только после явного согласия**.
4. Не меняй `search_anchors` и не ставь `search_anchors_confirmed: true` — это этап `/qa-anchors`.
