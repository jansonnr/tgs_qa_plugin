---
name: qa-zephyr-browse
description: Просмотр дерева папок Zephyr Scale (MCP get_folder_tree)
---

Run skill **`qa-zephyr-cache`** — режим **browse**.

1. Прочитай `project_key` из `.qa/materials/manifest.json` или спроси у пользователя.
2. Вызови MCP `get_folder_tree` (и при необходимости `get_folder`).
3. Покажи дерево на русском; **не** вызывай `search_test_cases` по якорям без `/qa-anchors`.
4. Предложи `/qa-zephyr-select` для записи папок в manifest или `/qa-zephyr-sync-index` после confirm якорей.
