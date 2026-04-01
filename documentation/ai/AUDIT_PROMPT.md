# Daily Audit Prompt

> This is the prompt used by the daily audit scheduled task.
> Replace `{PROJECT_PATH}` with the absolute path to the project directory.
> Replace `{project-name}` with the project's kebab-case name.

---

You are running a daily code quality audit for the project at {PROJECT_PATH}.

## Instructions

1. Navigate to the project directory: `cd {PROJECT_PATH}`

2. Run these 9 checks and record the results:

### Check 1: TypeScript Errors
Run: `npx tsc --noEmit 2>&1 | tail -5`
Count the number of errors reported.
- **PASS:** 0 errors
- **FAIL:** 1+ errors
Record the error count as the Value.

### Check 2: Lint Issues
Run: `npx next lint 2>&1`
Count errors (E) and warnings (W) separately.
- **PASS:** 0 errors and 0-5 warnings
- **WARN:** 0 errors and 6+ warnings, OR 1-2 errors
- **FAIL:** 3+ errors
Record as "XE / YW" format.

### Check 3: TODO/FIXME Count
Run: `grep -rn "TODO\|FIXME\|HACK\|XXX" src/ --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" | grep -v node_modules | wc -l`
- **PASS:** 0-5 items
- **WARN:** 6-15 items
- **FAIL:** 16+ items
Record the count as Value.

### Check 4: Test Results
Run: `npm test -- --passWithNoTests 2>&1`
Parse the output for pass/fail counts. If no test suite is configured, record "N/A" and WARN.
- **PASS:** 100% tests passing
- **WARN:** 90-99% passing OR no test suite configured
- **FAIL:** <90% passing or test runner crashes
Record as "X/Y passed" format.

### Check 5: Security Audit
Run: `npm audit --json 2>&1`
Parse JSON output for vulnerability counts by severity.
- **PASS:** 0 vulnerabilities
- **WARN:** Only low or moderate vulnerabilities
- **FAIL:** Any high or critical vulnerabilities
Record total vulnerability count.

### Check 6: Unused Dependencies
Check `package.json` dependencies against actual imports in `src/`.
For each dependency in `dependencies` (not devDependencies), search for imports:
`grep -r "from ['\"]PACKAGE" src/ --include="*.ts" --include="*.tsx" | head -1`
A dependency is "unused" if no import is found. Exclude framework internals: react, react-dom, next, @next/*, @types/*.
- **PASS:** 0 unused
- **WARN:** 1-3 unused
- **FAIL:** 4+ unused
Record the count.

### Check 7: Bundle Size
Run: `npx next build 2>&1` and parse the output for the total bundle size.
Look for the "First Load JS" size in the build output.
- **PASS:** Total first-load JS < 500KB
- **WARN:** 500KB - 1000KB
- **FAIL:** > 1MB
Record the largest route's first-load JS size.
**Note:** If build fails, record "BUILD FAILED" and FAIL.

### Check 8: Code Duplication
Search for duplicate code blocks in `src/`. Look for:
- Functions with identical bodies (>10 lines) across different files
- Copy-pasted blocks (identical sequences of 5+ non-trivial lines)
Use a heuristic approach: hash groups of 5 consecutive non-empty, non-import lines and look for matches.
- **PASS:** 0 duplicate blocks found
- **WARN:** 1-3 duplicate blocks
- **FAIL:** 4+ duplicate blocks
Record the count of duplicate blocks.

### Check 9: File Organization
Verify files follow the project's directory conventions:
- All React components are in `src/components/` or `src/app/`
- All API routes are in `src/app/api/`
- All utility functions are in `src/lib/` or `src/utils/`
- No source `.ts`/`.tsx` files directly in `src/` (should be in subdirectories)
- **PASS:** All files in expected directories
- **WARN:** 1-2 misplaced files
- **FAIL:** 3+ misplaced files
Record "All OK" or the count of misplaced files.

3. Write the results to `docs/AUDIT_LOG.md`.

Replace everything between `<!-- DASHBOARD:AUDIT:START -->` and `<!-- DASHBOARD:AUDIT:END -->` with:

```
| Check | Status | Value | Threshold | Details | Last Audited |
|---|---|---|---|---|---|
| TypeScript Errors | {STATUS} | {value} | 0 = PASS, 1+ = FAIL | npx tsc --noEmit | {YYYY-MM-DD HH:MM} |
| Lint Issues | {STATUS} | {value} | 0E ≤5W = PASS, 6+W = WARN, 3+E = FAIL | npx next lint | {YYYY-MM-DD HH:MM} |
| TODO/FIXME Count | {STATUS} | {value} | 0-5 = PASS, 6-15 = WARN, 16+ = FAIL | grep in src/ | {YYYY-MM-DD HH:MM} |
| Test Results | {STATUS} | {value} | 100% = PASS, 90%+ = WARN, <90% = FAIL | npm test | {YYYY-MM-DD HH:MM} |
| Security Audit | {STATUS} | {value} | 0 = PASS, low/mod = WARN, high/crit = FAIL | npm audit | {YYYY-MM-DD HH:MM} |
| Unused Dependencies | {STATUS} | {value} | 0 = PASS, 1-3 = WARN, 4+ = FAIL | package.json vs imports | {YYYY-MM-DD HH:MM} |
| Bundle Size | {STATUS} | {value} | <500KB = PASS, 500K-1M = WARN, >1M = FAIL | next build | {YYYY-MM-DD HH:MM} |
| Code Duplication | {STATUS} | {value} | 0 = PASS, 1-3 = WARN, 4+ = FAIL | Duplicate detection | {YYYY-MM-DD HH:MM} |
| File Organization | {STATUS} | {value} | All correct = PASS, 1-2 = WARN, 3+ = FAIL | Convention check | {YYYY-MM-DD HH:MM} |
```

4. Calculate the overall grade:
   - **A** = all PASS
   - **B** = 1-2 WARN, 0 FAIL
   - **C** = 3+ WARN, 0 FAIL
   - **D** = 1-2 FAIL
   - **F** = 3+ FAIL

5. Update the Audit History table. Add a new row at the TOP of the table between `<!-- DASHBOARD:AUDIT_HISTORY:START -->` and `<!-- DASHBOARD:AUDIT_HISTORY:END -->`. Keep only the last 30 rows. Format:

```
| {YYYY-MM-DD} | {GRADE} | {ts_errors} | {lint_value} | {todo_count} | {test_value} | {sec_count} | {unused_count} | {bundle_size} | {dup_count} | {file_org} |
```

6. Update the SCHEDULES table in `docs/TECH_STACK.md`: find the "Daily Audit" row and update its "Last Run" column to the current timestamp. Calculate "Next Run" as tomorrow at 08:30.

7. Commit: `git add docs/AUDIT_LOG.md docs/TECH_STACK.md && git commit -m "[audit] daily: code quality audit completed"`

8. Push to remote if configured: `git push`

**IMPORTANT:**
- Do NOT modify any other files.
- Do NOT start working on tasks or fixing issues found.
- If a command fails or times out, record the result as FAIL with details about the error.
- If `next build` takes more than 5 minutes, kill it and record "TIMEOUT" as FAIL.
- Only perform the audit and update the report.
