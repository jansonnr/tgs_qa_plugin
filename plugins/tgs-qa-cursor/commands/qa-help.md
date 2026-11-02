---
name: qa-help
description: Справка по командам QA-плагина и сквозному E2E-потоку
---

Покажи пользователю на **русском** краткую справку.

## Поток MVP

`/get-confluence-page` → (опц.) `/review-user-story` → `/create-test-case` → **`/key-words`** →
`/select-folders` → `/search-by-keyword` → `/compare-test-case-for-dedupe` → preview → «да, применить» → `/import-in-zephyr`

## Команды

| Группа | Команда | Назначение |
| --- | --- | --- |
| Базовые | `/qa-help` | Эта справка |
| | `/get-confluence-page` | Получить постановку с Confluence → `.qa/materials/` |
| | `/review-user-story` | Ревью user story / постановки (П1–П6) → `.qa/reviews/doc/` |
| | `/create-test-case` | Написать тест-кейсы → `.qa/drafts/testcases/` |
| | `/key-words` | Ключевые слова для поиска по тексту кейсов в Zephyr → manifest |
| Zephyr | `/search-test-case-in-zephyr` | Поиск по кейсам: дерево папок TMS |
| | `/select-folders` | Выбор папок Zephyr и проекта → `select_folders` в manifest |
| | `/search-by-keyword` | Поиск по ключевым словам → index-кэш |
| | `/update-test-case` | Подгрузить тела кейсов из Zephyr для diff после правок |
| | `/compare-test-case-for-dedupe` | Сравнить черновик с Zephyr → dedupe-plan.json |
| | `/import-in-zephyr` | Перенести/обновить утверждённые кейсы в Zephyr |

Канон: [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md). Приёмка: [docs/ACCEPTANCE-E2E.md](../docs/ACCEPTANCE-E2E.md).

**Вне MVP:** case review, Postman/API tests, RAG/KB, test run.
