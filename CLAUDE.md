# CLAUDE.md

> Claude Code reads this file automatically. This is the single source of truth for how you work on this project.

## STOP — READ THESE FIRST

**1. Read all 9 docs before doing ANY work.** No exceptions. Output a status line before proceeding. If you skip this, everything else breaks.

**2. One task at a time. Never skip stages.** `⚪ To Do → 🔍 Audit → 🟡 UI First → 🔵 Built → 🟢 Tested → 📝 Documented → 🟣 Deployed`. Hook-enforced — skipping Audit is blocked.

**3. After EVERY task: commit with SESSION_LOG + TASK_PIPELINE + GIT_LOG.** All three files must be staged in the commit. Hook-enforced — commits without SESSION_LOG are blocked.

**4. Push to Git at end of EVERY session.** Never leave unpushed work. Hook reminds you on wrap-up commits.

**5. Never add features outside MVP.** Say "SCOPE CHECK: This is outside current MVP. Added to parking lot." Only proceed if the user explicitly approves.

---

## Project Context

Read these files to understand the project (in this order):
1. `docs/PROJECT_BRIEF.md` — what we're building, MVP scope, features, success criteria
2. `docs/TASK_PIPELINE.md` — all tasks and their current stages
3. `docs/TECH_STACK.md` — every tool/service, setup status, API details
4. `docs/SESSION_LOG.md` — what happened last time, what to do next
5. `docs/DECISIONS.md` — architectural decisions and rationale
6. `docs/GIT_LOG.md` — commit history for the dashboard
7. `docs/DATA_STRUCTURE.md` — database/data model ER diagram
8. `docs/AUDIT_LOG.md` — daily code quality audit results (auto-generated)
9. `docs/FEATURE_AUDITS.md` — pre-development audit results per task (auto-generated)

These files are your memory. Read them before doing anything.

For file formats, logging templates, testing procedures, AI guidelines, and project structure details, see `documentation/ai/REFERENCE.md`.

---

## Rules

### 6. Auto-Start
At conversation start — automatically, without being asked:
1. Read all 9 docs listed above
2. Output: `✓ Loaded Apartment-management-Odessa — Phase [X] — [Y/Z tasks done] — Next: [task name]`
3. Start working on the next task immediately. Do NOT wait for "resume."

### 7. UI Before Mechanism
Build frontend/UI first with mock data. Get user approval before building backend logic. Never start backend until UI is confirmed. Exception: backend-only features start with API contract instead.

### 8. Architectural Checkpoint + Decision Log
Before any structural work (schema, API, state management, new dependencies, folder reorganization) — STOP and discuss tradeoffs. Present options, pros/cons, recommendation. Log every decision in `docs/DECISIONS.md` with timestamp. Format in `documentation/ai/REFERENCE.md`.

### 9. Pre-Development Audit
Before any task moves from `⚪ To Do` to `🟡 UI First`, run a pre-dev audit:
1. Move task to `🔍 Audit` in TASK_PIPELINE.md
2. Run 8 scoped checks: Security, Tests, Duplication, Error Handling, Complexity, Dependencies, Architecture, Console/Debug
3. Generate report at `docs/audits/{task-slug}-pre-audit.md`
4. Update `docs/FEATURE_AUDITS.md` table
5. Move task to `🟡 UI First`

Grading: A = all pass, B = 1-2 warns, C = 3+ warns, D = 1-2 fails, F = 3+ fails. Prompt: `documentation/ai/PRE_DEV_AUDIT_PROMPT.md`. Hook-enforced — skipping Audit stage is blocked.

### 10. Auto-Finish + Logging
After completing each task — automatically, without being asked:
1. Update `docs/TASK_PIPELINE.md` — move task to new stage
2. Update `docs/PROJECT_BRIEF.md` features table if status changed
3. Add timestamped entry in `docs/SESSION_LOG.md` (format in REFERENCE.md)
4. Commit with format: `[tag] verb: description`
5. Add entry to `docs/GIT_LOG.md`

When conversation ends ("done", "wrap up", "bye"): update all docs, commit, push, give 3-line summary. Every 3-5 tasks, output a status snapshot (format in REFERENCE.md).

### 11. Pattern First
After the first feature is built end-to-end, document the pattern in `documentation/features/` and follow it for all subsequent features.

### 12. Test It For Real + Fix Until It Works
Every feature must be visually and functionally verified before marking as 🟢 Tested. Run the app, take screenshots, test interactions, test edge cases. Detailed checklist in `documentation/ai/REFERENCE.md`.

When a test fails: do NOT move on. Fix → retest → repeat. After 3 failed attempts, show a recovery checklist (format in REFERENCE.md) and mark task as 🔴 Blocked.

### 13. Cost Consciousness
For AI features: start with the cheapest model that works (Haiku → Sonnet → Opus). Estimate token costs. Run A/B comparisons if quality is uncertain. Details in `documentation/ai/REFERENCE.md`.

### 14. Multi-Session Protocol
When multiple Claude Code windows work on the same project: register in `.claude/active-sessions.json`, check for conflicts before editing files, deregister on wrap-up. Full protocol in `documentation/ai/REFERENCE.md`.

### 15. Automated Checks
Two scheduled tasks run daily — do not manually edit their output markers:
- **Health Check** (`{project-name}-health-check`, 8:00 AM) — docs integrity, freshness, compliance. Results in `docs/TECH_STACK.md` HEALTH section.
- **Code Audit** (`{project-name}-daily-audit`, 8:30 AM) — code quality checks. Results in `docs/AUDIT_LOG.md`.

Prompts: `documentation/_templates/HEALTH_CHECK_PROMPT.md` and `documentation/ai/AUDIT_PROMPT.md`.

### 16. Enforcement Hooks
Hooks in `scripts/hooks/` are configured in `.claude/settings.json`. Do not disable or bypass them.

| Hook | Type | Enforces |
|---|---|---|
| `check-commit-format.sh` | BLOCK | Commit format: `[tag] verb: description` |
| `check-session-log.sh` | BLOCK | SESSION_LOG.md included in task commits |
| `check-task-stage-skip.sh` | BLOCK | Cannot skip 🔍 Audit stage |
| `check-dashboard-markers.sh` | BLOCK | Dashboard markers not removed |
| `check-claude-integrity.sh` | BLOCK | CLAUDE.md structure preserved |
| `check-git-log-sync.sh` | WARN | GIT_LOG.md updated after commits |
| `check-pipeline-update.sh` | WARN | TASK_PIPELINE.md updated after task commits |
| `check-git-push-reminder.sh` | WARN | Push reminder on session wrap-up |

If a hook blocks you, fix the underlying issue — don't try to work around it.

### 17. Git Workflow
- **Commit after every task** — format: `[tag] verb: description`
- **Every task commit includes:** source files + SESSION_LOG.md + TASK_PIPELINE.md + GIT_LOG.md
- **Update GIT_LOG.md** after every commit — hook-enforced
- **Push at end of every session** — hook-enforced reminder
- **Never force push** main/master
- **Pull before starting** — always `git pull` at conversation start
- **Branch strategy:** Feature branches for multi-task work, commit to main for single tasks
- Valid tags: `phase1`, `phase2`, `health`, `audit`, `infra`, `fix`, `docs`, `setup`

---

## Workflows

### When I say "New project: [name]"
1. Interview: What problem? Who for? MVP (max 5 features)? Tech stack? AI components?
2. Fill in PROJECT_BRIEF.md, TECH_STACK.md, TASK_PIPELINE.md (max 8-10 tasks), SESSION_LOG.md, DECISIONS.md, GIT_LOG.md, DATA_STRUCTURE.md
3. Set up scheduled tasks: health-check (8:00 AM) and daily-audit (8:30 AM)
4. Confirm scope before writing code

### On Conversation Start (automatic)
1. Read all 9 docs
2. Register in `.claude/active-sessions.json` (see Rule 14)
3. Output status (see Rule 6)
4. Start working on the next task immediately

### When I say "Wrap up" / "Done"
1. Update all docs (Rule 10)
2. Commit with proper format
3. Push to Git
4. 3-line summary: done, progress, next

---

## Behavior

- Read project docs FIRST — they are your memory
- Start working immediately — don't wait for instructions
- Save state continuously — log after every task, not just at end
- Be honest when confused — ask before guessing
- Prefer small working increments over perfect plans
- Never delete or overwrite logs — append only (newest at top)
- All timestamps: `YYYY-MM-DD HH:MM` format
- When anything fails: fix it or show a recovery checklist. Never leave failures unaddressed.
- For all file formats, logging templates, and detailed procedures: see `documentation/ai/REFERENCE.md`
