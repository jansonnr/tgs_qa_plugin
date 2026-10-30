---
name: qa-apply-zephyr
description: Apply dedupe-plan to Zephyr with create and update after explicit user confirmation. Writes apply log under .qa/drafts/testcases/.
---

# Apply to Zephyr

## Prompts (required)

1. Read and follow [prompts/_source-trust.md](../../prompts/_source-trust.md).
2. Apply flow per [prompts/apply-zephyr.md](../../prompts/apply-zephyr.md).

## Gate

Read [config/limits.yaml](../../config/limits.yaml): `dedupe_auto_update_allowed` MUST stay `false` in MVP.

Import label for Zephyr create: [config/zephyr-defaults.yaml](../../config/zephyr-defaults.yaml) (`AI_Cursor` by default). Preview must show this label; MCP enforces it on create and rejects other `labels` in create rows.

Check required MCP tools: `prepare_apply`, `apply_plan`, `resume_apply`, `reconcile_apply`. If a tool is missing, stop and name it. Do not call `create_test_case` / `update_test_case` directly: the server rejects them without an apply token.

Do not call mutate tools until all of the following hold:

- No plan item has unresolved `action: ask`.
- No two items share a `target_key`.
- Draft `revision` equals plan `draft_revision`; plan has `run_id`.
- Update and delete rows carry `baseline_fingerprint` from a fresh `get_test_case`.
- Required create fields are in the preview (folder, status, priority). Defaults `Draft` and `Normal` are shown, not silent.
- User wrote «да, применить» after this preview fingerprint.
- Step changes on update also need «заменить шаги». `steps` is the full list: unchanged steps stay with their ids. Empty `steps` clears steps; a missing field leaves them untouched.

## Steps

1. Read `<run-id>.dedupe-plan.json` and the draft `<run-id>.json`. Refuse if revisions differ.
2. Call `prepare_apply` with `plan` and `draft`. Build the preview table from the returned `target` and `operations` (no Zephyr mutation yet). Store `preview_fingerprint` and `plan_hash` on the plan.
3. After confirm call `apply_plan` with the same `plan`, the same `draft` and the returned token. Do not mutate Zephyr any other way.
4. The server writes the journal (`started` before each request). `success` is never repeated. 401/403 and 429 stop the batch; the tail stays `not_run`. Continue with `resume_apply` and the **same** token (after `retry_after` for 429).
5. `RECONCILE_REQUIRED`: ask QA to check Zephyr, then `reconcile_apply` with `created` + `zephyr_key` or `absent`. Never guess.
6. `ALREADY_CREATED`: the row changed after a successful create; turn it into an update of `zephyr_key` via a new preview.
7. Sanitize errors: code and short message, no token.
8. Remind: link new/updated keys in Jira manually if the team process requires it.
