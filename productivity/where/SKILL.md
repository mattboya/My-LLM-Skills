---
name: where
description: Use when the user types /where, or asks where this thread stands - what it was about, whether its work shipped, got implemented or is still in flight, or whether the thread is safe to close - including when they return to a thread after time away.
---

# /where

One thread's status: what it was about, why it matters, whether its work reached the remote, and whether the thread can close. Read-only (a `git fetch` aside) until the user picks an option. For every open thread in a repo at once, use open-thread-summary.

## 1. List what this thread produced

From the whole conversation, compaction summary included:
- the main piece of work, in the user's terms (a thread with side questions still has one topic)
- commit SHAs, branches, PR numbers, Jira keys, WORK_QUEUE.md entry IDs, files edited
- loose ends: decisions the user has not answered, work Claude said it would do later, checks Claude said someone should run (a first live run, a test on a device)

Nothing produced → the verdict is "Discussion only". Go to step 3.

## 2. Check each item now

The thread's last message can be days old, so answer from the checks, not from the conversation. `<default>` is `git symbolic-ref --short refs/remotes/origin/HEAD` (minus `origin/`).

| Item | Check | Shipped when |
|---|---|---|
| all | `git fetch -q` first | — |
| commit | `git merge-base --is-ancestor <sha> origin/<default>` | exit 0. Not found by SHA (rebased, squashed)? Search `git log origin/<default> --oneline -i --grep=<key or subject>` before you call it unshipped |
| files | `git status --short -- <files>` and `git log origin/<default>..HEAD --oneline` | clean and nothing ahead. Another session can share this checkout: a dirty file counts only if its diff is this thread's work. A gitignored queue (`**In git:** no`) never shows here |
| PR | `gh pr view <n> --json state,mergedAt,url` | MERGED |
| Jira | one search for all keys, status only | Done |
| queue ID | `grep -n '^### <ID>\b' WORK_QUEUE.md` (headings only: other entries' notes mention IDs) | no heading. Then find the ID in the newest `*-wave*.md` beside the queue to learn its PR and ticket keys, and check those too |

Run the checks together where you can; a wave doc or PR can name new keys, so a second round is fine. A check that cannot run (no access, no network) is "unknown". Do not guess.

## 3. Report in exactly this shape

**<topic, 3–6 words>: <Shipped | In flight | Not started | Discussion only>**
- **What:** 1–2 sentences: the ask and what got done, and by whom when another session or a wave built it.
- **Why it matters:** 1–2 sentences in business terms.
- **Evidence:** one line of the checks that ran, e.g. `a1b2c3d` on origin/main · PR #12 merged · PROT-120–131 Done. Use ranges for long lists.
- **Left:** each open item and where it lives (PR, ticket, queue entry, wave follow-ups), or "nothing". Merged is not released: name a pending release or hand check here.
- **Close:** "Safe to close" or "Not yet: <what would be lost>".

Safe to close = everything shipped, or everything still open lives outside this thread. "Not yet" = uncommitted work of this thread, unpushed commits, or a loose end from step 1 that exists only in this conversation. A loose end the checks show was settled elsewhere, or a command the user can simply rerun, does not count.

Push status comes only from this check's fetch. Never write a push banner for work this thread did not push.

## 4. Ask the next step as a click-to-answer question

- Safe to close → "Archive this thread?" (Archive / Keep open). On Archive, use the host's archive tool on this session as the last call of the turn (Claude desktop: `archive_session` with `"self"`). No such tool → say the thread can be closed.
- Not yet → recommend the one step that moves the loose ends somewhere durable: a `/queue` entry where the repo has a WORK_QUEUE.md, otherwise a ticket, an issue or a line in the repo's docs; or commit, push, or answer the open decision. Second option: "Close anyway". Act only on the user's pick.
