# AGENTS.md

Репозиторий — Cursor QA plugin (не Test Generator Suite).

- Требования и решения: `docs/`.
- Канонические тексты LLM: `prompts/` (skills ссылаются на файлы, не дублируют длинные промпты).
- Пользовательская документация на русском; идентификаторы в skills/rules — на английском.
- Не добавлять в MVP: case review, Postman/API tests, RAG, test run, лимиты TGS.
- Артеfactы QA в **workspace** пользователя под `.qa/`; в этом репо только плагин.
- Команды: `commands/`; skills: `skills/`; промпты: `prompts/`; примеры JSON: `schemas/`.
- MCP сервер не в этом репо — контракт расширений: `docs/MCP-EXTEND.md`.
