# Pre-Development Audit Prompt

> This is the prompt used before starting development on any task.
> Replace `{PROJECT_PATH}` with the absolute path to the project directory.
> Replace `{project-name}` with the project's kebab-case name.

---

You are running a pre-development code audit for a task in the project at {PROJECT_PATH}.

## Input

The task name will be provided as an argument when this audit is invoked. If not provided, read `docs/TASK_PIPELINE.md` and audit the first task with stage `⚪ To Do`.

## Instructions

1. Navigate to the project directory: `cd {PROJECT_PATH}`

2. Read the task description from `docs/TASK_PIPELINE.md`. Identify:
   - The task name and any notes
   - The likely affected files/directories based on the task description
   - Related existing code patterns

3. Run these 8 checks scoped to the affected area and record the results:

### Check 1: Security Scan
Search the affected files for:
- `dangerouslySetInnerHTML` without DOMPurify sanitization
- SQL injection risks (raw queries, string interpolation in queries)
- Missing authentication/authorization checks on API routes
- Hardcoded secrets or credentials
- XSS vectors (unescaped user input in rendering)
- **PASS:** 0 security issues found
- **WARN:** 1-2 low-severity issues
- **FAIL:** Any high-severity issues (XSS, SQL injection, auth bypass)
Record the issue count.

### Check 2: Test Coverage
Check for existing test files covering the affected modules:
- Look for `*.test.ts`, `*.test.tsx`, `*.spec.ts` files in related directories
- Check if the affected functions/components have corresponding tests
- **PASS:** Test files exist for affected modules
- **WARN:** Partial coverage (some modules lack tests)
- **FAIL:** No test files exist for the affected area
Record as "X/Y modules covered".

### Check 3: Code Duplication
Search for duplicate code blocks in the affected files:
- Functions with identical bodies (>10 lines) across different files
- Copy-pasted blocks (identical sequences of 5+ non-trivial lines)
- Similar patterns that should be abstracted into shared utilities
- **PASS:** 0 duplicate blocks found
- **WARN:** 1-3 duplicate blocks
- **FAIL:** 4+ duplicate blocks
Record the count of duplicate blocks.

### Check 4: Error Handling
Check the affected area for proper error handling:
- Missing `error.tsx` files for route segments
- Missing `loading.tsx` files for route segments
- Raw `fetch()` calls without try-catch or error handling
- Unhandled promise rejections
- Missing input validation at API boundaries
- **PASS:** Proper error handling in place
- **WARN:** 1-2 gaps in error handling
- **FAIL:** 3+ gaps or critical missing error handling
Record the issue count.

### Check 5: Code Complexity
Analyze affected files for complexity issues:
- Files exceeding 500 lines
- Functions exceeding 50 lines
- Nesting depth exceeding 4 levels
- Cyclomatic complexity concerns
- **PASS:** All within limits
- **WARN:** 1-2 files or functions at the threshold
- **FAIL:** Any file >800 lines or function >100 lines
Record the largest file's line count.

### Check 6: Dependencies
Check if the task will require new dependencies or if affected code uses deprecated/problematic ones:
- Deprecated packages in the affected area
- Multiple packages solving the same problem
- Missing peer dependencies
- **PASS:** No dependency concerns
- **WARN:** 1 minor concern (e.g., outdated but functional)
- **FAIL:** Deprecated critical dependency or conflict
Record "OK" or the issue count.

### Check 7: Architecture
Verify the affected area follows project conventions:
- Components in correct directories (`src/components/` or `src/app/`)
- API routes in `src/app/api/`
- Utility functions in `src/lib/` or `src/utils/`
- Consistent patterns with similar existing features
- Separation of concerns (business logic not in components)
- **PASS:** Follows all patterns
- **WARN:** 1-2 minor deviations
- **FAIL:** Significant pattern violations
Record "OK" or the issue count.

### Check 8: Console/Debug
Search affected files for debug artifacts:
- `console.log`, `console.warn`, `console.error` statements (non-intentional)
- Commented-out code blocks (>5 lines)
- Debug flags or test-only code in production paths
- `TODO` or `FIXME` markers in the affected area
- **PASS:** Clean code, no debug artifacts
- **WARN:** 1-3 minor debug artifacts
- **FAIL:** 4+ debug artifacts
Record the count.

4. Calculate the overall grade:
   - **A** = all PASS
   - **B** = 1-2 WARN, 0 FAIL
   - **C** = 3+ WARN, 0 FAIL
   - **D** = 1-2 FAIL
   - **F** = 3+ FAIL

5. Generate the audit report at `docs/audits/{task-slug}-pre-audit.md`:

Convert the task name to a slug (lowercase, hyphens for spaces, remove special characters).

```markdown
# Pre-Development Audit: {Task Name}
**Date:** YYYY-MM-DD HH:MM
**Grade:** {A-F}
**Affected Area:** {directories/files identified}

## Summary
{1-2 sentence overview of findings}

## Findings

### Security
- {finding or "No issues found"}

### Test Coverage
- {finding or "Adequate coverage"}

### Code Duplication
- {finding or "No duplicates"}

### Error Handling
- {finding or "Proper handling"}

### Code Complexity
- {finding or "Within limits"}

### Dependencies
- {finding or "No concerns"}

### Architecture
- {finding or "Follows patterns"}

### Console/Debug
- {finding or "Clean"}

## Recommendations
1. {actionable item before starting development}
2. {actionable item}

## Pre-Development Checklist
- [ ] Review security findings before implementation
- [ ] Ensure test files exist for affected modules
- [ ] Follow existing patterns identified above
```

6. Update `docs/FEATURE_AUDITS.md`:

Add or update the row for this task in the table between `<!-- DASHBOARD:FEATURE_AUDITS:START -->` and `<!-- DASHBOARD:FEATURE_AUDITS:END -->`. Keep newest at the top.

```
| {Task Name} | {GRADE} | {security_count} | {test_coverage} | {duplication_count} | {complexity_value} | {YYYY-MM-DD} |
```

7. Update the task stage in `docs/TASK_PIPELINE.md` from `⚪ To Do` to `🔍 Audit`.

8. Commit: `git add docs/audits/ docs/FEATURE_AUDITS.md docs/TASK_PIPELINE.md && git commit -m "[audit] pre-dev: {task-name} audit completed"`

**IMPORTANT:**
- Do NOT fix any issues found — only report them.
- Do NOT start working on the task itself.
- Do NOT modify source code files.
- If a check cannot be performed (e.g., no source files yet for a new feature), record as WARN with "N/A — new feature" note.
- Only perform the audit and generate the report.
