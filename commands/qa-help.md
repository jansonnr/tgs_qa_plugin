---
name: qa-help
description: Справка по командам QA-плагина и сквозному E2E-потоку
---

Покажи пользователю на **русском** краткую справку.

## Поток MVP

`/qa-materials` → (опц.) `/qa-doc-review` → `/qa-testcases` → **`/qa-anchors`** →
`/qa-zephyr-sync-index` → `/qa-dedupe` → preview → «да, применить» → `/qa-apply-zephyr`

## Команды

| Группа | Команда | Назначение |
| --- | --- | --- |
| Базовые | `/qa-help` | Эта справка |
| | `/qa-materials` | Jira, Confluence, файлы → `.qa/materials/` |
| | `/qa-doc-review` | Анализ документации → `.qa/reviews/doc/` |
| | `/qa-testcases` | Черновик кейсов → `.qa/drafts/testcases/` |
| | `/qa-anchors` | Якоря dedupe после черновика → manifest |
| Zephyr | `/qa-zephyr-browse` | Дерево папок TMS (без search по якорям) |
| | `/qa-zephyr-select` | Выбор `project_key` / `search_folders` в manifest |
| | `/qa-zephyr-sync-index` | Index-only cache по папке |
| | `/qa-zephyr-refresh` | Тела кейсов для update/ask из plan |
| | `/qa-dedupe` | dedupe-plan.json |
| | `/qa-apply-zephyr` | create/update в Zephyr после confirm |

Канон: [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md). Приёмка: [docs/ACCEPTANCE-E2E.md](../docs/ACCEPTANCE-E2E.md).

**Вне MVP:** case review, Postman/API tests, RAG/KB, test run.
