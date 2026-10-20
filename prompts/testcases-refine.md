Пользователь просит изменить существующий черновик `.qa/drafts/testcases/<run-id>.json`.

Правила:

1. Сохрани `draft_id` у уже существующих кейсов. Новый кейс получает следующий свободный id; удалённый id не занимай снова.
2. Внеси **только** запрошенные правки; не удаляй кейсы без явной просьбы.
3. Перед записью скопируй текущий файл в `<run-id>.v<revision>.json`. Затем обнови канонический `<run-id>.json`: тот же `run_id`, `revision + 1`.
4. Существенное изменение (`name`, `preconditions`, `steps`, `test_data`, `expected_results`, состав кейсов) — поставь в manifest `search_anchors_confirmed: false`. Смена только `labels`, `folder`, `status`, `priority` confirm не сбрасывает; обнови `anchors_draft_revision` на новый номер.
5. Кратко перечисли на русском, что изменилось (добавлено/удалено/переименовано) и какой теперь `revision`.
6. Соблюдай `rules/qa-testcase-format.mdc` и `manifest.clarification`.
7. Если есть дополнение проекта (см. [testcases.md](testcases.md) — `.qa/` или `manifest.testcases_project_prompt`), учитывай его при правках стиля, labels и `folder`.
