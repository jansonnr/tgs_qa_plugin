Предложи **search_anchors** для dedupe в Zephyr Scale — **после** того как есть черновик
тест-кейсов (`.qa/drafts/testcases/<run-id>.json`).

Источники для фраз (3–10):

1. **Имена** и ключевые формулировки из **шагов/expected** черновика.
2. Материалы (Jira, Confluence) — модуль, API, сущности, **без** дублирования всего текста задачи.
3. Опционально уже известные `project_key`, `search_folders` из manifest (Jira Component и т.д.).

Якоря — для поиска **похожих существующих** кейсов в TMS по name/контексту. Это **не** ключи QA-T*.

Покажи список на русском с обоснованием (откуда фраза: draft name, material id).

**Не вызывай** API Zephyr (search, sync-index), пока пользователь не подтвердил или не отредактировал якоря.

QA на этом шаге подтверждает **фразы**. Папки (`search_folders`, `project_key`) подтверждаются отдельно на `/qa-zephyr-select`. Для dedupe нужны оба.

После подтверждения сохрани в `materials/manifest.json`:

- `search_anchors`; `search_folders` и `project_key` — только если QA уточнил их здесь
- `search_anchors_confirmed: true`
- `anchors_draft_run_id`: `<run-id>` черновика
- `anchors_draft_revision`: текущий `revision` обёртки черновика

Если черновик изменили существенно — якоря недействительны (`search_anchors_confirmed: false`), пока QA не подтвердит их снова.
