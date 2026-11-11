---
name: queue-batch-page
description: Use when a batch of work from a project's WORK_QUEUE.md has just finished (the dispatched items have landed or been held back), before telling the user the batch is done or wrapping up the session.
---

# Queue batch page

Every finished batch of `WORK_QUEUE.md` work ends with one stakeholder page, published before the wrap-up message, whether or not the user asked for it.

1. **Harvest, then delete.** From each entry the batch finished, collect its `🔴 Decision open` blocks. A leftover defect becomes its own entry; a constraint on later work moves onto the pending entry it affects. Then delete the finished entries.
2. **Build the page** from `~/.agents/skills/queue/batch-page-template.html`. Its header comment has the rules: plain words and business outcomes, one card per open decision saying what was actually built (`data-built`), grouped by theme, "Fill in my recommendations" above the first question and "Copy my answers" after the last. No open decisions → delete the questions section; the page still records what shipped and how to check it.
3. **Publish it** privately with the Artifact tool, `icon: "list"`, capabilities exactly as the template's comment gives them. Run one ArtifactData `list` of `answers` on the new url to confirm the store answers.
4. **List it** under `## Awaiting answers` at the end of `WORK_QUEUE.md`: `- YYYY-MM-DD — <url> — <n> questions`. With `**In git:** no` the file has no undo, so always: copy it to the scratchpad, build the new version there, `cmp` the live file against your copy, then `cp`.
5. **Link it** in the wrap-up, and tell the user to share it with stakeholders at *Can interact* or *Can edit*.

Stakeholders answer on the page; the user's `/queue answers` turns those answers into queue changes.
