---
name: qa-materials
description: Prepare requirement materials for QA workflows in .qa/materials. Use for Jira, Confluence, files, and text before doc review or test case generation. Does not require dedupe anchors (those come after testcase draft).
---

# QA materials

Read [REQUIREMENTS.md](../../docs/REQUIREMENTS.md). Warn on very large material sets; no hard TGS numeric caps.

## Prompts (required)

1. Read and follow [prompts/_source-trust.md](../../prompts/_source-trust.md).

**Do not** propose or require `search_anchors` here — use `/qa-anchors` after `/qa-testcases`.

## MCP (when applicable)

- Confluence: `get_confluence_page` (pageId or URL). Long pages come in portions: while `content_complete` is `false`, call again with `text_offset = next_offset` and append. Do not finish the material until `content_complete: true`, or the user explicitly agrees to a partial read — then mark the material `"complete": false`.
  With `include_linked_pages=true` show every entry of `link_warnings` (link without space, ambiguous or failed page) to the user; such a page is not part of the material.
- Jira issue: `get_jira_issue` when available in MCP (see [MCP-GAP-ANALYSIS.md](../../docs/MCP-GAP-ANALYSIS.md)).
- Credentials: только `set_credentials`. Не открывать файл конфига MCP и не писать токены в `.qa/`, чат или аргументы tools.

## Steps

1. Ensure `.qa/materials/` exists. One manifest = one task. If a new Jira key differs from
   existing `provenance`, ask the user to replace the set or stop. Do not merge two tasks.
2. For each source (text, file, Jira, Confluence): normalize to `.qa/materials/<id>.json`
   per [schemas/material.example.json](../../schemas/material.example.json): stable `id`, `type`, `provenance`, `fetched_at`, `text`.
   Replace tokens, passwords and `Bearer` values in `text` with `[secret]`; do not echo the secret.
3. Update `manifest.json`: `materials[]`, `clarification`, `run_id`. Write only under `.qa/`.
4. **Optional (no confirm gate):** suggest `project_key` and `search_folders` from Jira/Component
   for later TMS scope — save only if user agrees; leave `search_anchors_confirmed: false`.
5. **Do not** call Zephyr search or dedupe from this skill.
6. Do not attach images to the model automatically; tell the user to `@`-attach if needed.
7. Suggest next: `/qa-doc-review` and/or `/qa-testcases`, then `/qa-anchors` before dedupe.
