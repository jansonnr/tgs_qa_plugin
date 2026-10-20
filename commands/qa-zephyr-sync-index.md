---
name: qa-zephyr-sync-index
description: Index-only кэш кейсов Zephyr по папке из manifest
---

Run skill **`qa-zephyr-cache`** — режим **sync-index**.

- `project_key` и folder из manifest или ввод пользователя.
- Перед **`search_test_cases` по якорям** проверь `search_anchors_confirmed === true`; иначе stop → `/qa-anchors`.
- Browse / list in folder по `search_folders` допустим без якорей.
- Пиши `.qa/cache/zephyr/<projectKey>/folders/<folderId>/index.json` (summary only).
