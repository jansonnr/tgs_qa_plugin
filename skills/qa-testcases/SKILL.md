---
name: qa-testcases
description: Generate structured test case draft JSON from .qa materials and optional doc review. Output under .qa/drafts/testcases/.
---

# Generate test cases

## Prompts (required)

1. Read and follow [prompts/_source-trust.md](../../prompts/_source-trust.md).
2. If user asked to **refine** an existing draft: [prompts/testcases-refine.md](../../prompts/testcases-refine.md).
3. Otherwise follow [prompts/testcases.md](../../prompts/testcases.md): read [prompts/testcases-base.md](../../prompts/testcases-base.md), then optional project overlay under `.qa/` (`manifest.testcases_project_prompt` or `prompts/testcases-project.md`).

## Steps

1. Read `materials/manifest.json`; honor `clarification` first.
2. Optional: `reviews/doc/<run-id>.json` if `--after-doc-review`.
3. Number materials in the user message; one cohesive suite, not N unrelated suites per file.
4. Output object `{ run_id, revision, cases }` to `.qa/drafts/testcases/<run-id>.json` per rules/qa-testcase-format.
   New generation → new `run_id` (`YYYYMMDD-<slug>`), `revision: 1`, stable `draft_id` from `"1"`.
5. Human-readable `<run-id>.md` alongside JSON — **полный** текст всех кейсов по [testcases-base.md](../../prompts/testcases-base.md) § «Markdown»; не только оглавление.
6. If XMind material present: add `coverage-xmind.json` when paths are known.
7. Substantial change (`name`, preconditions, steps, test_data, expected_results, add/remove case):
   set `search_anchors_confirmed: false`. Labels, folder, status, priority alone do not reset confirm;
   update `anchors_draft_revision` to the new revision.
8. Suggest next step: **`/qa-anchors`** (then folder select, sync-index and `/qa-dedupe`). Do not skip anchors.
9. Refine is an explicit user command: snapshot current file to `<run-id>.v<revision>.json`, then write
   the canonical `<run-id>.json` with `revision + 1`. Do not leave the new text only in the snapshot.
