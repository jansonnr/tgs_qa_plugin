---
name: qa-anchors
description: Propose and confirm Zephyr dedupe search anchors from testcase draft and materials. Run after /qa-testcases, before sync-index and /qa-dedupe.
---

# QA anchors (dedupe scope)

Read [REQUIREMENTS.md](../../docs/REQUIREMENTS.md) §5.

## Prompts (required)

1. [prompts/_source-trust.md](../../prompts/_source-trust.md)
2. [prompts/anchors.md](../../prompts/anchors.md)

## Preconditions

- `.qa/drafts/testcases/<run-id>.json` exists (user may pass run-id).
- `materials/manifest.json` exists.

## Steps

1. Load the draft JSON; extract distinctive terms from case `name` and significant steps.
2. Merge with hints from materials; propose 3–10 `search_anchors` and optional `search_folders` / `project_key`.
3. Show list in Russian; **do not** call Zephyr search or sync-index until user confirms or edits.
4. On confirm: write manifest fields per `prompts/anchors.md`, including `anchors_draft_run_id` and `anchors_draft_revision` from the draft envelope.
5. Suggest next: `/qa-zephyr-sync-index`, then `/qa-dedupe`.

## Re-run

If user only edits anchors without a new draft, update manifest and set `search_anchors_confirmed: true` after confirm.

If `search_anchors_confirmed` is false, `/qa-dedupe` and sync-index **must stop** and point here.
