---
name: qa-apply-zephyr
description: Apply dedupe-plan в Zephyr после явного подтверждения пользователя
---

Run skill **`qa-apply-zephyr`** after user confirmed dedupe-plan.

Требуется явное «да, применить» **после** preview-таблицы в чате. Нерешённый `ask` останавливает весь apply.

Читай `config/limits.yaml`: `dedupe_auto_update_allowed: false` — update только после свежего diff и confirm. Журнал пишется по каждому пункту; `unknown` не повторять как create.
