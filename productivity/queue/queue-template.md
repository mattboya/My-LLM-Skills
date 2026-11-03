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

**Open questions live on one page.** Decisions the code can't settle, and the
decisions each run made for you, go on one open-questions page per queue, at one
link. Each `/wave` handoff, `/queue unblock` and `/queue questions` update it in
place (`~/.agents/skills/queue/batch-page-template.html` has the rules). First
come the questions that need you before something is built, then decisions built
differently from my recommendation, merge decisions, Waiting items, and decisions
built as recommended, folded by run to skim. A question stays until you answer
it, later work settles it, or it no longer applies; the page lists what closed
without you, and why. Stakeholders answer on the page; `/queue answers` applies
an answer to an entry still waiting here, or turns an answer that differs from
what was built into a follow-up entry. The page's link is the first line under
`## Awaiting answers` at the end of this file.

**`🔴 Decision open`** on an entry means it was written using the recommended
answer, and the work builds that. The question stays on the open-questions page
until someone answers it.

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
- **PR:** — (set by /queue promote: the pull request this ships in)
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

<!-- First line: the open-questions page.
- Open questions — <page url> — <n> open (rolled YYYY-MM-DD)
Then any older pages, still read until each of their questions is settled. -->
