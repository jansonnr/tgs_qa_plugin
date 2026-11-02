---
name: update-test-case
description: Обновить существующие кейсы согласно правкам после агента (подгрузка тел из Zephyr для diff)
---

Run skill **`qa-zephyr-cache`** — режим **refresh**.

1. Прочитай `<run-id>.dedupe-plan.json`; собери ключи с action `update` или `ask`.
2. Для каждого вызови MCP `get_test_case` → `.qa/cache/zephyr/<projectKey>/cases/<key>.json`.
3. Используй для diff перед `/import-in-zephyr`; mutate в TMS **не** вызывай (запись — только `/import-in-zephyr` после confirm).
