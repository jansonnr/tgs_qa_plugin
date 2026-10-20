---
name: qa-materials
description: Сбор материалов (Jira, Confluence, файлы, текст) в .qa/materials
---

Run skill **`qa-materials`**.

- Нормализуй источники в `.qa/materials/<id>.json` и обнови `manifest.json`.
- **Не** предлагай и **не** требуй `search_anchors` — якоря только после `/qa-testcases` через `/qa-anchors`.
- **Не** вызывай Zephyr search или dedupe.
- Опционально (без gate): предложи `project_key` и `search_folders` — сохраняй только после согласия пользователя.

Следующий шаг: `/qa-doc-review` и/или `/qa-testcases`.
