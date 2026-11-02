# E2E приёмка MVP (одна Jira-задача)

**Предусловия:** Cursor с плагином; MCP `user-zephyr-scale` с credentials; тестовый
`project_key` и папка, выбранные через `/select-folders` (не боевой регресс).
Модель с достаточным контекстом. Созданные кейсы удаляет QA вручную: DELETE в MVP нет.

Наблюдаемый результат FR — файл из [REQUIREMENTS.md](REQUIREMENTS.md) §6 или явный stop в чате.

## Успешный сценарий

1. **Постановка** — `/get-confluence-page`: одна страница Confluence (и при необходимости ключ Jira) →
   `.qa/materials/manifest.json` (якоря **не** обязательны). Второй ключ Jira не дописывается молча.
2. **Doc review** (опционально) — `/review-user-story` → `.qa/reviews/doc/<run-id>.json` + `.md`.
3. **Кейсы** — `/create-test-case` → `.qa/drafts/testcases/<run-id>.json` (обёртка `run_id`, `revision`, `cases`, ≥5 кейсов).
4. **Якоря** — `/key-words`: предложение из черновика + материалов → QA подтверждает фразы →
   `search_anchors_confirmed: true`, `anchors_draft_run_id`, `anchors_draft_revision`.
5. **Папки** — `/select-folders`: QA подтверждает `project_key` и `select_folders`.
6. **Index TMS** — `/search-by-keyword` → index без полных testScript и с полем `complete`.
7. **Dedupe** — `/compare-test-case-for-dedupe` → `<run-id>.dedupe-plan.json`. При кандидате действие `ask`, не сразу `update`.
   QA переводит нужные строки в `update` или `skip`.
8. **Apply** — preview с folder, status, priority и fingerprint; QA пишет «да, применить».
   Если шаги update отличаются от кейса в TMS — ещё «заменить шаги».
   Журнал `<run-id>-apply-log.json` появляется до конца пачки. Итог: create и/или update.

## Успех

- Все артефакты на месте, у каждого пункта журнала конечный `status`.
- В Zephyr видны новые ключи и обновлённый кейс (если был update).
- Dedupe не вызывал search на весь проект одним maxResults=5000.
- Нет шагов case review, Postman/API tests, knowledge base, test run.

## Не в этой приёмке (ревью п. 1)

- Полнота индекса при больше чем одной странице и вложенных папках.
- Дубль, который совпадает с новым кейсом только шагами, а не названием.
- Сохранение `id` шагов, когда QA меняет один шаг существующего кейса.
