---
name: search-by-keyword
description: Поиск по ключевым словам — index-кэш кейсов Zephyr в выбранных папках
---

Run skill **`qa-zephyr-cache`** — режим **sync-index**.

- `project_key` и folder из manifest или ввод пользователя.
- Перед **`search_test_cases` по ключевым словам** проверь `search_anchors_confirmed === true`; иначе stop → `/key-words`.
- Browse / list in folder по `select_folders` допустим без ключевых слов.
- Пиши `.qa/cache/zephyr/<projectKey>/folders/<folderId>/index.json` (summary only).
