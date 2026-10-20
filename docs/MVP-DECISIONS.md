# Решения MVP

**Статус:** Accepted (v0.3), дополнения v0.3.4 по ревью требований (кроме п. 1)

## Scope MVP

| Включено | Исключено |
| --- | --- |
| Materials; якоря **после** testcases (`/qa-anchors`) | Рецензия кейсов Zephyr (`/qa-case-review`) |
| Doc review | API-тесты / Postman |
| Генерация черновика | База знаний, RAG, `--with-knowledge` |
| Dedupe + apply (create/update) | Test run, last test result |
| Zephyr cache (index + bodies по ключам) | Числовые лимиты TGS в config |

## Архитектура

- **Один Cursor-плагин** (`tgs-qa-cursor`): skills, commands, rules. Исполняемого кода нет.
- MCP: переиспользовать и при необходимости **расширять** `user-zephyr-scale`
  (update, list folder cases, Jira issue) — **не** отдельные плагины parsers/tms/kb.
- Артефакты **только** в `.qa/`; `cache/zephyr/` в `.gitignore`.
- Одна активная задача (один manifest) на workspace.

## Dedupe / update

- Сильное совпадение → **`ask`**. `update` и `skip` только после выбора QA.
- `skip` только если тело кандидата прочитано и QA явно выбрал skip.
- Ошибка или неполный индекс (`complete: false`) не превращаются в `create`.
- Нерешённый `ask` блокирует **весь** apply.
- Два черновика на один `target_key` не применяются.
- Update в Zephyr после diff и «да, применить». Неизменённые шаги в PUT не отправлять.
  Изменение шагов — только после отдельной фразы «заменить шаги». Сохранение `id` шагов не обещается.
- Match по уже полученным кандидатам. Способ добыть этот набор — открытый вопрос ревью п. 1.

## Согласие и сбои записи

- Согласие — фраза «да, применить» на конкретный fingerprint preview и `draft_revision`.
- Карточка одобрения MCP в Cursor — дополнительный канал. При auto-run её нет: это граница гарантии.
- Прямой HTTP с токеном из конфига MCP плагин не закрывает.
- Журнал apply пишется по каждой операции. `unknown` (таймаут, 5xx, пустой ответ) не повторять как create.
- 401/403 и второй 429 останавливают пачку.

## Корпоративная установка

Team marketplace и Required rules для Cursor Teams — **вне MVP**; достаточно
`~/.cursor/plugins/local` и инструкции в README.

## Закрыто

| Было открыто | Решение |
| --- | --- |
| Auto-update без diff | **Нет** — update только после diff и «да» (`dedupe_auto_update_allowed: false`) |
| Порог fuzzy-match для auto-`update` | **Нет порога.** Любой кандидат → `ask`, решение за QA |
| Team marketplace | Вне MVP |
| Test run | Вне MVP |
| Один MCP vs несколько | **Один** Zephyr MCP + расширения; parsers — позже в том же MCP |
| Кто пишет `.qa/` и кто вызывает Zephyr | Агент пишет `.qa/`; Zephyr только через MCP. Гарантии и обходы — REQUIREMENTS §2.1 |
| Одна или несколько задач в workspace | **Одна** активная задача |
| Нерешённый ask | Блокирует весь apply |
| Потерянный ответ POST | `unknown`, create не повторять до сверки или решения QA |

## Открыто

- Ревью п. 1: вариант Zephyr, отбор кандидатов без поиска по фразам, полнота вложенных папок и страниц, сопоставление `id` шагов, права Jira/Zephyr.

## v0.3.2

- Якоря dedupe перенесены с `/qa-materials` на этап после `/qa-testcases` (`/qa-anchors`).
