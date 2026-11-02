---
name: search-test-case-in-zephyr
description: Поиск по всем кейсам в Zephyr (навигация по папкам TMS)
---

Run skill **`qa-zephyr-cache`** — режим **browse**.

1. Прочитай `project_key` из `.qa/materials/manifest.json` или спроси у пользователя.
2. Вызови MCP `get_folder_tree` (и при необходимости `get_folder`).
3. Покажи дерево на русском; **не** вызывай `search_test_cases` по ключевым словам без `/key-words`.
4. Предложи `/select-folders` для записи папок в manifest или `/search-by-keyword` после confirm ключевых слов.
