# JSON-схемы артеfactов (примеры)

Канон полей — [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md) §5. Файлы здесь — **примеры** для агента и QA. Перед записью в TMS агент сверяет обязательные поля по §5.2. Отдельная команда валидации — фаза 1.1.

| Файл | Путь в workspace |
| --- | --- |
| [manifest.example.json](manifest.example.json) | `.qa/materials/manifest.json` |
| [material.example.json](material.example.json) | `.qa/materials/<id>.json` |
| [doc-review.example.json](doc-review.example.json) | `.qa/reviews/doc/<run-id>.json` |
| [draft-testcases.example.json](draft-testcases.example.json) | `.qa/drafts/testcases/<run-id>.json` |
| [testcases-project.example.md](testcases-project.example.md) | `.qa/prompts/testcases-project.md` (дополнение промпта) |
| [dedupe-plan.example.json](dedupe-plan.example.json) | `.qa/drafts/testcases/<run-id>.dedupe-plan.json` |
| [apply-log.example.json](apply-log.example.json) | `.qa/drafts/testcases/<run-id>-apply-log.json` |
| [zephyr-index.example.json](zephyr-index.example.json) | `.qa/cache/zephyr/.../index.json` |
| [zephyr-meta.example.json](zephyr-meta.example.json) | `.qa/cache/zephyr/meta.json` |
