# Work Queue

**Tracker:** {{TRACKER}}

Add to this file with `/queue <what's wrong or what you want>`. Point Claude at
it to do the work: **"work the queue in WORK_QUEUE.md"**, or type **`/wave`**. It reads the list,
groups items that touch the same files into one unit, and fans the independent
units out to parallel agents.

Only `## Ready` gets worked: it is exactly what `/wave` builds. `## Waiting` holds
items that are ready to build except for something outside the code (a person, a
decision, a measurement, legal); each says what in a `**Waiting on:**` line, and
moves back to Ready when that's resolved. Everything else sits in `## Later` until
you move it up.

**Only work that is not done yet lives here — no `## Done`, no results, no
status banners.** An item leaves this file the moment its code lands on the main
branch, not when its review closes. The tracker is the record of what shipped.
If a shipped item constrains future work, put that note on the pending item it
affects. A follow-up found while shipping becomes its own entry, never a note
left on the finished one.

**Touches** is the field that matters most — it decides what can run in
parallel. Two items with overlapping files get merged into one agent, not two.

**Before working or ticketing an item, check that it isn't already done —
against the code, not the entry text.** Entries rot, and a stale one costs more
than a missing one. Already shipped → delete the entry. Partly done → rewrite it
down to what is genuinely left and name what closed the rest. Already ticketed
but not done → point the entry at the ticket, and read the ticket's assignee and
comments before working it.

**When a batch finishes, publish one batch page.** Build it from
`~/.agents/skills/queue/batch-page-template.html` (its header comment has the
rules): what shipped and why it matters, how to check it by hand, and the
decisions in three parts. **Not built yet** comes first: every `🔴 Decision open`
still on an entry here, so answering them moves queued work forward. Then the
decisions the batch's entries carried or the work raised: **Built differently
from my recommendation** as full cards, left blank for you to pick, and **Built
as recommended** pre-filled with what was built and folded to one line each, to
skim and change only if you want to. Publish it privately,
then add its link under `## Awaiting answers` at the end of this file.
Stakeholders answer on the page; `/queue answers` applies an answer to an entry
still waiting here, or turns an answer that differs from what was built into a
follow-up entry.

**`🔴 Decision open`** on an entry means it was written using the recommended
answer, and the work builds that. The question shows under Not built yet on
every batch page until someone answers it.

**This file is gitignored, so it has no history and no undo.** Never edit it in
place: build the new version in a scratch copy, check that the live file still
matches the copy you started from, then copy the new version over it.

---

## Ready

<!-- Copy this block per item. -->

<!--
### AREA-1 — short title
- **Type:** bug | feature
- **Layer:** frontend | backend | both
- **Ticket:** — (filled in when the wave is dispatched)
- **Touches:** path/to/file, path/to/its.test
- **Now:** what it does today (for a bug: the symptom, and how to see it)
- **Want:** what it should do instead
- **Done when:** the observable check that proves it — a test, a screen state, an API shape
- **By hand:** the steps only a human can do — look and feel, env steps, anything a test can't see
- **Notes:** anything non-obvious (a decision already made, a thing not to touch, an open decision)
-->

## Waiting

<!-- Same format, plus a first line: - **Waiting on:** who or what, and for what. -->

## Later

<!-- Same format. Nothing here gets worked until you move it up. -->

## Awaiting answers

<!-- One line per batch page still collecting answers:
- YYYY-MM-DD — <page url> — <n> questions
/queue answers deletes a line once every question on its page is settled. -->
