# AGENTS.md

Репозиторий — Cursor QA plugin (не Test Generator Suite).

- Требования и решения: `docs/`.
- Код плагина: `plugins/tgs-qa-cursor/` (commands, skills, prompts, rules, schemas, MCP).
- Канонические тексты LLM: `plugins/tgs-qa-cursor/prompts/` (skills ссылаются на файлы, не дублируют длинные промпты).
- Не добавлять в MVP: case review, Postman/API tests, RAG, test run, лимиты TGS.
- Артеfactы QA в **workspace** пользователя под `.qa/`; в этом репо только плагин.
- Team marketplace: `.cursor-plugin/marketplace.json`, `pluginRoot`: `plugins`.
- MCP-сервер Zephyr: `plugins/tgs-qa-cursor/zephyr-scale-mcp/`, подключение в `plugins/tgs-qa-cursor/mcp.json`. Контракт tools: `docs/MCP-EXTEND.md`.
