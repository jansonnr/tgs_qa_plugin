# Changelog

## Unreleased

Доработки по ревью мейнтейнера 0.3.5 (C01–C25).

- Apply: история операции по `case_id` не зависит от текста соседних строк; успешный create не повторяется и после правки строки (`ALREADY_CREATED`). `unknown`/`started` create и повреждённый журнал требуют сверки.
- Новый tool `reconcile_apply`: `created` + ключ (сервер сверяет name) или `absent`.
- Журнал: `started` пишется до запроса; если журнал недоступен, запрос не уходит (`LOG_UNAVAILABLE`). Сбой журнала в `.qa/` не теряет результат. `not_sent` после `started` не блокирует повтор.
- Блокировка apply — средствами ОС (`msvcrt`/`fcntl`): снимается при падении владельца, без гонки по пустому lock-файлу.
- `prepare_apply` требует `plan.run_id`, фиксирует один origin и один проект для плана и возвращает `target` и `operations` для preview. Параметр `draft` переносит в строки плана шаги, `test_data`, `expected_results`, `preconditions`, `folder`, `status`, `priority`.
- Валидация до preview: поля шагов, пустые status/priority, `labels` в create (ставится только `AI_Cursor`), `project_key`, `baseline_fingerprint` для delete.
- Update: маскированные и усечённые поля без правки сохраняются из Zephyr; правка с `[secret]`/`…` отклоняется. Delete перечитывает кейс и сверяет baseline.
- Индекс: строки без ключа — неизвестная схема (`api_error`); `search_status`/`complete` не теряются в ответе с ошибкой; `sync_testcase_index` принимает `project_id` для подпапок другого проекта.
- Matcher принимает кейс черновика как есть (строковые шаги, `test_data`, `preconditions`) и учитывает отличия предусловий.
- `apply_plan`/`resume_apply` помечены `destructive_hint` (план может содержать delete).
- Документация 429, контракт `steps` (полный список), чтение Confluence порциями в `/qa-materials`.

## 0.3.6

- Структура **team marketplace**: `.cursor-plugin/marketplace.json`, плагин в `plugins/tgs-qa-cursor/`.

## 0.3.5

- MCP Zephyr Scale перенесён в `zephyr-scale-mcp/`; подключение через корневой `mcp.json` и `plugin.json` (`mcpServers`).

## 0.3.4

- Лицензия MIT для публикации.
- Промпты testcase: `testcases-base.md`, опциональный overlay только в `.qa/prompts/`.
- Требования v0.3.4: ревью (кроме п. 1 про поиск Zephyr) — ответственность, ревизии черновика, dedupe через `ask`, журнал apply с `unknown`, политика данных, сбойные сценарии приёмки.

## 0.3.3

- Все slash-команды с frontmatter; добавлены `/qa-zephyr-browse`, `/qa-zephyr-select`, `/qa-zephyr-refresh`.
- Исправлена команда `/qa-materials` (без якорей на этапе materials).
- Skill `qa-zephyr-cache`: browse/select/sync-index/refresh; rules gate + config.
- Примеры JSON в `schemas/`; docs `MCP-EXTEND.md`.

## 0.3.2

- Якоря dedupe: после `/qa-testcases`, команда `/qa-anchors`; materials без обязательных якорей.
- Manifest: `anchors_draft_run_id`; FR-ANC обновлены в docs.
- REQUIREMENTS: матрица FR (MAT/TC/ANC/ZEP/DED/PUB/…), диаграммы Mermaid (E2E, якоря, dedupe, apply).

## 0.3.1

- Каталог `prompts/` с каноническими текстами для LLM; skills ссылаются на файлы.

## 0.3.0

- Scope: убраны case review, API tests, knowledge/RAG, test run.
- Решения: единый плагин, только `.qa/`, без числовых лимитов TGS.
- Отдельный репозиторий; документы в `docs/`; удалены skills/commands postman и case-review.

## 0.2.0

- Требования: dedupe-plan, якоря задачи, sync-index, apply create+update в Zephyr.
- Skeleton: skills, commands, rules, schemas, пример MCP.

## 0.1.0

- Начальный черновик требований (ориентир TGS).
