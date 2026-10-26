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

Import label for Zephyr create: [config/zephyr-defaults.yaml](../../config/zephyr-defaults.yaml) (`AI_Cursor` by default). Preview must show this label; MCP enforces it on create (draft `labels` are not copied to TMS).

Check required MCP tools (`create_test_case`, and `update_test_case` if the plan has updates). If a tool is missing, stop and name it.

Do not call mutate tools until all of the following hold:

- No plan item has `action: ask`.
- No two items share a `target_key`.
- Draft `revision` equals plan `draft_revision`.
- Required create fields are in the preview (folder, status, priority). Defaults `Draft` and `Normal` are shown, not silent.
- User wrote «да, применить» after this preview fingerprint.
- Step changes on update also need «заменить шаги». Unchanged steps are omitted from the PUT.
- An existing apply-log with `in_progress` is resumed, not started as a second batch.

For status/priority on create: use `list_project_metadata` when MCP provides it; else values from the draft or ask the user.

## Steps

1. Read `<run-id>.dedupe-plan.json` and the draft envelope. Refuse if revisions differ.
2. Preview table in chat (no MCP mutate yet). Store `preview_fingerprint` on the plan.
3. After confirm, for each item write the log **before** the next item:
   - mark `in_progress`
   - `create` → `create_test_case` → `ok` or `failed` or `unknown`
   - `update` → fresh `get_test_case`; on `updated` mismatch → `conflict` and no PUT; else `update_test_case`
   - `skip` → `skipped`
4. `ok` is never repeated. `unknown` is not retried as create. 401/403 stop the batch. 429 retries the same item once (wait `Retry-After`, or at most 60s); a second 429 stops the batch. Other item errors continue the batch.
5. Sanitize errors: code and short message, no token.
6. Resume with «продолжить» only for `pending` items of the same fingerprint. Treat a leftover `in_progress` as `unknown`.
7. Remind: link new/updated keys in Jira manually if the team process requires it. The plugin does not delete cases.
