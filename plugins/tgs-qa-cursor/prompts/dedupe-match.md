Сопоставь каждый кейс черновика с уже полученным набором кандидатов Zephyr.

Используй подтверждённые `search_anchors`, непустые `search_folders` и `project_key` из `materials/manifest.json`.
`anchors_draft_run_id` и `anchors_draft_revision` должны совпадать с `run_id` и `revision` черновика, иначе остановись.

Способ, которым набран набор кандидатов (поиск API, локальный индекс, метки), этой инструкцией не выбирается. Если индекс с `"complete": false`, выгрузка оборвалась или API вернуло ошибку — `search_status`: `incomplete` или `error`. В этом случае **не** ставь `create` и не пиши «дублей нет».

Правила match, когда `search_status: complete`:

1. Общие якоря сужают набор один раз. Каждый кейс сравнивай по его **name** и, после чтения тела, по шагам. Не требуй, чтобы все якоря нашлись в каждом кейсе.
2. Узкий search по якорям, если он используется; **не** один запрос на весь проект с огромным `maxResults`.
3. Для top 1–3 кандидатов вызови `get_test_case` до выбора действия. Diff строй по этому ответу.
4. `action`:
   - нет кандидата → `create`. В rationale: «в выбранной области похожих не найдено».
   - есть кандидат → `ask` (даже при высоком сходстве). Не ставь `update` сам.
   - `update` или `skip` — только после явного выбора QA. Тогда `resolved_from: ask`, `resolved_by: user`, `body_read: true`.
   - `skip` без прочитанного тела запрещён. В rationale укажи, какие шаги существующего кейса закрывают черновик.
5. Два пункта с одним `target_key` оставь в `ask` и напиши про конфликт.
6. Запиши `.qa/drafts/testcases/<run-id>.dedupe-plan.json`: `run_id`, `draft_revision`, `search_status`, `items[]` (`draft_id`, `draft_name`, `action`, `target_key`, `body_read`, `rationale`).

**Не вызывай** `create_test_case` / `update_test_case` в этом сценарии.

Покажи таблицу на русском. Для `ask` — краткий diff (шаги / expected) по свежему чтению.
