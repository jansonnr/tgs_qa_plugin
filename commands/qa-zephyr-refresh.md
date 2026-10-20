---
name: qa-zephyr-refresh
description: Подгрузка полных тел кейсов Zephyr для ключей из dedupe-plan
---

Run skill **`qa-zephyr-cache`** — режим **refresh**.

1. Прочитай `<run-id>.dedupe-plan.json`; собери ключи с action `update` или `ask`.
2. Для каждого вызови MCP `get_test_case` → `.qa/cache/zephyr/<projectKey>/cases/<key>.json`.
3. Используй для diff перед `/qa-apply-zephyr`; mutate в TMS **не** вызывай.
