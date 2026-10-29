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

Check required MCP tools: `prepare_apply`, `apply_plan`, `resume_apply`. If a tool is missing, stop and name it. Do not call `create_test_case` / `update_test_case` directly: the server rejects them without an apply token.

Do not call mutate tools until all of the following hold:

- No plan item has `action: ask`.
- No two items share a `target_key`.
- Draft `revision` equals plan `draft_revision`.
- Required create fields are in the preview (folder, status, priority). Defaults `Draft` and `Normal` are shown, not silent.
- User wrote «да, применить» after this preview fingerprint.
- Step changes on update also need «заменить шаги». В PUT уходит полный список шагов: неизменённые остаются со своими id. Пустой `steps` — это очистка, отсутствие поля — не трогать шаги.
- An existing apply-log with `in_progress` is resumed, not started as a second batch.

For status/priority on create: use `list_project_metadata` when MCP provides it; else values from the draft or ask the user.

## Steps

1. Read `<run-id>.dedupe-plan.json` and the draft envelope. Refuse if revisions differ.
2. Preview table in chat (no MCP mutate yet). Store `preview_fingerprint` on the plan.
3. After confirm call `prepare_apply` with the plan, then `apply_plan` with the same plan and the returned token. Do not mutate Zephyr any other way.
4. `apply_plan` writes the journal itself. `ok` is never repeated. `unknown` / unfinished create is not posted again. 401/403 stop the batch without downgrading an earlier success. 429 pauses the rest of the batch. Resume the same run with `resume_apply`, not a new create.
5. Sanitize errors: code and short message, no token.
6. Resume with «продолжить» only for `pending` items of the same fingerprint. Treat a leftover `in_progress` as `unknown`.
7. Remind: link new/updated keys in Jira manually if the team process requires it. The plugin does not delete cases.
