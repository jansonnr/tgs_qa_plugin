---
name: get-confluence-page
description: Получить постановку с Confluence
---

Run skill **`qa-materials`**.

Пользователь хочет забрать постановку. Источник — страница Confluence (URL или pageId): вызови `get_confluence_page` и сохрани нормализованный материал в `.qa/materials/`.

- Jira, файл или вставленный текст принимай так же, если пользователь их дал.
- **Не** предлагай и **не** требуй `search_anchors` — якоря только после `/create-test-case` через `/key-words`.
- **Не** вызывай Zephyr search или dedupe.
- Опционально (без gate): предложи `project_key` и `select_folders` — сохраняй только после согласия пользователя.

Следующий шаг: `/review-user-story` и/или `/create-test-case`.
