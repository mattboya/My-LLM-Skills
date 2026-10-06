## Wave protocol

<!-- /wave reads this section. The five "###" blocks below Setup are pasted into agent
prompts as-is, with {REPO}, {SP} (the run's scratchpad), {BASE} and {HOT_FILES} filled in.
Keep each block self-contained. Tighten it after every wave with what the wave taught. -->

### Setup

- **Branch:** {{BRANCH}}. **Author:** {{GIT_AUTHOR or "any"}}.
- **Isolation:** one shared checkout. No worktrees, no branches.
- **Push:** never. The wave stops at the local branch; push only on the user's explicit OK for that push.
- **Tickets:** {{TRACKER RULES — which project, assignee, sprint, lifecycle; or "none: the queue ID is the commit key, decoded in QUEUE_IDS.txt"}}. Queue IDs never go into the tracker, nor into commits when there is one.
- **Helpers:** `~/.agents/skills/wave/helpers/{wave-commit.sh,lock.sh}`{{, plus any project snapshot helpers}}. Wave 0 copies them into `{SP}/wave/` and writes `{SP}/wave/wave.env` with `WAVE_REPO={REPO}`, `WAVE_BRANCH={{BRANCH}}`{{, WAVE_AUTHOR=...}}.
- **Deploy notes to carry into the handoff:** {{restarts, migrations, anything a human must do before or after release}}.

### Shared rules

SHARED-CHECKOUT RULES (non-negotiable: up to 16 agents are editing this same checkout right now; no worktrees, no branches, NO PUSH):
1. Edit only the files your unit needs. Before editing a file outside your lane's ownership, run `git -C {REPO} status --porcelain -- <file>`: if it has uncommitted changes you did not make, another lane owns it right now; do not touch it, record it in crossLaneNotes.
2. NEVER run: git stash, checkout, restore, reset, clean, rebase, merge, push, commit -a, commit --amend, add -A / add ., plain git commit, any branch or worktree command.
3. Commit ONLY with the helper: write the message to {SP}/commit-msgs/<label>-<slice>.txt, then `{SP}/wave/wave-commit.sh <msgfile> <path> <path> ...` naming EVERY file of that slice (new, test, deleted).
4. Format and lint ONLY your own paths: {{FORMAT/LINT COMMANDS, per path}}. Never a repo-wide fixer.
5. Tests in the shared tree are targeted only: {{TARGETED TEST COMMANDS}}. Never pipe a gate into tail/head and trust $?: redirect to a file and echo the exit code. A failure in a file you did not touch is probably another lane mid-edit: re-run once later, then report it.
6. NEVER run: dependency installs, database migrations against the dev database, code generators that rewrite shared files, {{PROJECT-SPECIFIC BANS}}. Never touch the running dev app.
7. The work queue and the wave doc are READ-ONLY for you.
{{8. A MIGRATIONS or SHARED-REGISTRY rule, if the project has them; otherwise delete this line}}

### Hot files

HOT-FILE LOCKS ({SP}/wave/lock.sh): the files listed for this wave may only be edited while you hold their lock. `lock.sh acquire <your label> <path>...` takes every path you need in one call; hold them from your first edit to the commit that contains them; `lock.sh release <your label> <path>...` right after. Never hold a lock across a review or while waiting on another agent. This wave's hot files: {HOT_FILES}

### Method

METHOD (project): {{DOCS TO READ, PROJECT SKILLS TO ACTIVATE, CODE CONVENTIONS}}. Commit line 1 uses {{the ticket key | the queue ID}} of the item.

### Snapshot

ISOLATION (reviewers and verifiers): do not edit anything under {REPO}. Make a disposable copy of committed code: `SNAP={SP}/snap/<unique-name>; mkdir -p "$SNAP"; git -C {REPO} archive HEAD | tar -x -C "$SNAP"`, then {{COPY OR LINK DEPENDENCIES, e.g. cp -Rc node_modules}}. Run tests and experiments inside $SNAP. Never commit from a snapshot. Clean up after.

### Gates

GATES, each redirected to a file with its exit code echoed (never piped): {{FULL TEST, TYPECHECK, LINT, FORMAT and E2E COMMANDS}}. Fix a failing test's premise, never weaken or delete the test.
