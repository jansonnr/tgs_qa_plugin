Генерация черновика тест-кейсов — **два слоя промпта**.

## 1. База (обязательно)

Прочитай и следуй [testcases-base.md](testcases-base.md) — универсальная методика плагина.

## 2. Проект (опционально)

Если в workspace есть файл дополнения проекта, прочитай его **после** базы и примени как **уточнение**, не как замену формата:

| Приоритет пути | Файл |
| --- | --- |
| 1 | Путь из `manifest.testcases_project_prompt` (относительно `.qa/`), если задан |
| 2 | Иначе `.qa/prompts/testcases-project.md`, если существует |

**При конфликте правил:**

1. `manifest.clarification`
2. Дополнение проекта (термины, папки Zephyr, обязательные labels, шаблоны данных, приоритеты)
3. Материалы задачи
4. [testcases-base.md](testcases-base.md)

Дополнение проекта **не отменяет**: `_source-trust.md`, `rules/qa-testcase-format.mdc`, запрет выдумывать требования и API.

Если файла проекта нет — работай только по базе.

Шаблон для копирования в workspace: [schemas/testcases-project.example.md](../schemas/testcases-project.example.md).
