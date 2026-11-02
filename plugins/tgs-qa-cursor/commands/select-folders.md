---
name: select-folders
description: Выбрать папки Zephyr (и project_key) для поиска и импорта
---

Run skill **`qa-zephyr-cache`** — режим **select**.

1. При необходимости сначала `/search-test-case-in-zephyr` для навигации по папкам.
2. Уточни у пользователя `project_key` и пути/ID папок (`search_folders`).
3. Обнови `.qa/materials/manifest.json` **только после явного согласия**.
4. Не меняй `search_anchors` и не ставь `search_anchors_confirmed: true` — это этап `/key-words`.
