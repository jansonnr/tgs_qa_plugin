---
name: qa-dedupe
description: Match draft test cases against Zephyr index and build dedupe-plan with create, update, skip, or ask. Use after /qa-testcases or on existing draft JSON.
---

# QA dedupe

## Prompts (required)

1. Read and follow [prompts/_source-trust.md](../../prompts/_source-trust.md).
2. Match and plan per [prompts/dedupe-match.md](../../prompts/dedupe-match.md).

## Preconditions

- `.qa/drafts/testcases/<run-id>.json` exists.
- `materials/manifest.json` has `search_anchors_confirmed: true`, non-empty `search_anchors`, non-empty `search_folders`, and `project_key`.
  If anchors are missing — **stop** and run `/qa-anchors`. If folders are missing — **stop** and run `/qa-zephyr-select`.
- `anchors_draft_run_id` and `anchors_draft_revision` MUST match this draft, unless user explicitly confirmed mismatch in chat.
- Read [rules/qa-manifest-gate.mdc](../../rules/qa-manifest-gate.mdc) and [config/limits.yaml](../../config/limits.yaml).
- Index: run `/qa-zephyr-sync-index` or use existing `.qa/cache/zephyr/.../index.json`. If `complete` is false or the read failed, `search_status` is `index_incomplete` or `api_error`, not `ok`.

## Steps

1. Load `cases[]` from the draft envelope. Keep existing `draft_id`; do not renumber.
2. If index `complete` is false or the fetch errored, set `search_status` to `index_incomplete` or `api_error` and do **not** emit `create`.
3. Otherwise match each case inside the candidate set (shared anchors narrow the set once; each case is compared by its own name). Fetch `get_test_case` for the top 1–3 before choosing an action. Use `baseline_fingerprint` from that response; do not hash the masked text yourself.
4. Write `.qa/drafts/testcases/<run-id>.dedupe-plan.json` with `run_id`, `draft_revision`, `search_status`, and `operations` (`case_id`, `name`, `action`, `test_case_key`, `baseline_fingerprint` for update/delete). `prepare_apply` also accepts the older `items` / `draft_id` / `search_status: complete` shape and adapts it. Do not copy steps into the plan: `prepare_apply` takes them from the draft passed as `draft`.
   For `match_test_case_candidates` pass draft cases as-is (`draft_id`, `name`); results come back with the same `case_id`. A high score or a shared name is a candidate for `ask`, never proof of «no duplicate» or of equivalence.

5. Any candidate → `ask`. Set `update` or `skip` only after the user chooses (`resolved_by: user`, `body_read: true`). Two items must not share a `target_key` without staying on `ask`.
6. Present a table in Russian; for `ask` show a diff from the fresh `get_test_case`.
7. Do **not** call create/update MCP tools in this skill.
