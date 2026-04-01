# Health Check Prompt

> This is the prompt used by the daily health check scheduled task.
> Replace `{PROJECT_PATH}` with the absolute path to the project directory.
> Replace `{project-name}` with the project's kebab-case name.

---

You are running a daily health check for the project at {PROJECT_PATH}.

## Instructions

1. Read these project files to assess health:
   - `CLAUDE.md`
   - `index.html`
   - `docs/PROJECT_BRIEF.md`
   - `docs/TASK_PIPELINE.md`
   - `docs/TECH_STACK.md`
   - `docs/SESSION_LOG.md`
   - `docs/DECISIONS.md`
   - `docs/GIT_LOG.md`
   - `docs/DATA_STRUCTURE.md`

2. Run these 8 checks and determine PASS, WARN, or FAIL for each:

### Check 1: File existence
Check that all 9 files above exist.
- **PASS:** All present
- **WARN:** 1-2 missing
- **FAIL:** 3+ missing

### Check 2: Dashboard markers
Verify these marker pairs exist in the correct files:
- `DASHBOARD:FEATURES` + `DASHBOARD:PROCESS_FLOW` in `docs/PROJECT_BRIEF.md`
- `DASHBOARD:TASKS` in `docs/TASK_PIPELINE.md`
- `DASHBOARD:STACK` + `DASHBOARD:STACK_DETAILS` + `DASHBOARD:SCHEDULES` + `DASHBOARD:HEALTH` in `docs/TECH_STACK.md`
- `DASHBOARD:GIT_LOG` in `docs/GIT_LOG.md`
- `DASHBOARD:DATA_STRUCTURE` in `docs/DATA_STRUCTURE.md`
- **PASS:** All present
- **WARN:** 1-2 missing
- **FAIL:** 3+ missing

### Check 3: Session log freshness
Find the most recent `YYYY-MM-DD` date in `docs/SESSION_LOG.md`.
- **PASS:** Within 7 days
- **WARN:** 8-21 days ago
- **FAIL:** 22+ days ago or no entries

### Check 4: Git log maintenance
Check last entry date in `docs/GIT_LOG.md`. Also run `git log -1 --format=%cd --date=short` and compare.
- **PASS:** Within 14 days
- **WARN:** 15-30 days stale
- **FAIL:** 30+ days stale or empty

### Check 5: Task pipeline health
Parse the TASKS table in `docs/TASK_PIPELINE.md`. Count tasks with stage containing "Blocked".
- **PASS:** 0 blocked tasks
- **WARN:** 1 blocked task
- **FAIL:** 2+ blocked tasks

### Check 6: Tech stack completeness
Parse `docs/TECH_STACK.md` — the STACK table and STACK_DETAILS section.
- Check for tools with `Uses API: Yes` but no `API Key Expires` value
- Check for expired API keys (date in the past)
- **PASS:** All complete, no expired keys
- **WARN:** 1-2 incomplete entries
- **FAIL:** Expired API keys or 3+ incomplete

### Check 7: CLAUDE.md integrity
Verify `CLAUDE.md` contains these key sections:
- `## Rules` heading (or `## Rules (Non-Negotiable)`)
- At least rules 1 (Auto-Start), 4 (One Task), 9 (Auto-Finish), 10 (Per-Task Logging)
- `## File Formats` heading
- `## Workflows` heading
- **PASS:** All present
- **WARN:** 1-2 missing
- **FAIL:** 3+ missing or Rules section absent

### Check 8: Schedule health
Parse the SCHEDULES table in `docs/TECH_STACK.md`. For active jobs, check if Last Run is overdue given the Frequency.
- **PASS:** No overdue active jobs (or no schedules)
- **WARN:** 1 overdue job
- **FAIL:** 2+ overdue jobs

3. Write the results to `docs/TECH_STACK.md`. Replace everything between `<!-- DASHBOARD:HEALTH:START -->` and `<!-- DASHBOARD:HEALTH:END -->` with:

```
| Check | Status | Details | Last Checked |
|---|---|---|---|
| File existence | {STATUS} | {X}/9 files present | {YYYY-MM-DD HH:MM} |
| Dashboard markers | {STATUS} | {X}/{TOTAL} markers found | {YYYY-MM-DD HH:MM} |
| Session log freshness | {STATUS} | Last entry {N} days ago | {YYYY-MM-DD HH:MM} |
| Git log maintenance | {STATUS} | {details} | {YYYY-MM-DD HH:MM} |
| Task pipeline health | {STATUS} | {N} blocked tasks | {YYYY-MM-DD HH:MM} |
| Tech stack completeness | {STATUS} | {details} | {YYYY-MM-DD HH:MM} |
| CLAUDE.md integrity | {STATUS} | {details} | {YYYY-MM-DD HH:MM} |
| Schedule health | {STATUS} | {details} | {YYYY-MM-DD HH:MM} |
```

4. Update the SCHEDULES table in `docs/TECH_STACK.md`: find the "Daily Health Check" row and update its "Last Run" column to the current timestamp (`YYYY-MM-DD HH:MM`). Calculate the "Next Run" as tomorrow at 08:00.

5. Commit: `git add docs/TECH_STACK.md && git commit -m "[health] daily health check completed"`

6. Push to remote if configured: `git push`

**IMPORTANT:** Do NOT modify any other files. Do NOT start working on tasks. Only perform the health check and update the report.
