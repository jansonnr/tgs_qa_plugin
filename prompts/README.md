# Промпты плагина

Канонические тексты для LLM. Skills **обязаны** читать соответствующий файл перед
генерацией. Редактируйте здесь — не дублируйте длинные формулировки в `skills/`.

| Файл | Сценарий |
| --- | --- |
| [_source-trust.md](_source-trust.md) | Общие правила (в начале каждого run) |
| [anchors.md](anchors.md) | Якоря dedupe (`/qa-anchors`, после testcases) |
| [doc-review.md](doc-review.md) | Бинарное ревью постановки (П1–П6, UPD, замечания) → `.qa/reviews/doc/` |
| [testcases-base.md](testcases-base.md) | Методика кейсов и чек-листов для плагина (слой 1, `.qa/`, TMS) |
| [testcases.md](testcases.md) | Генерация: база + опциональный overlay в `.qa/` |
| [testcases-refine.md](testcases-refine.md) | Доработка существующего черновика |
| [dedupe-match.md](dedupe-match.md) | Сопоставление с Zephyr index |
| [apply-zephyr.md](apply-zephyr.md) | Apply create/update в TMS |

Пользовательские данные задачи — в `.qa/` workspace, не в этом каталоге.
