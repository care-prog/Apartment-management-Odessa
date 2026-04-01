# [Feature Name] — AI Feature Doc

> One doc per AI-powered feature. Required before marking as 📝 Documented.

## Status: ⚪ Draft / 🟡 In Development / 🟢 Production

## What It Does

_1-2 sentences. What does this AI feature do for the user?_

## Model & Cost

| Field | Value |
|---|---|
| Model | haiku / sonnet / opus |
| Why this model | _Justification — why not cheaper?_ |
| Avg input tokens | - |
| Avg output tokens | - |
| Est. cost/request | - |
| Monthly budget | - |
| Prompt file | `prompts/[name]-v1.md` |

## How It Works

### User Flow
1. User does X
2. System sends Y to AI
3. AI returns Z
4. User sees result

### Technical Flow
```
[Input] → [Pre-processing] → [AI Call] → [Post-processing] → [Output]
```

## Prompt Strategy

- **System prompt:** What role/context is set
- **User prompt:** What dynamic content is injected
- **Output format:** JSON / markdown / plain text
- **Guardrails:** What prevents bad outputs (validation, filtering, fallbacks)

## Error Handling

| Scenario | Handling |
|---|---|
| Rate limit hit | Retry with backoff / queue |
| Empty response | Fallback message to user |
| Malformed output | Re-parse or retry once |
| Timeout | Show loading state, retry |
| Harmful content | Filter and log |

## Evaluation Criteria

How do we know this feature is working well?

| Criteria | Target | How Measured |
|---|---|---|
| Accuracy | _e.g., 90%+_ | Manual review of N samples |
| Relevance | _e.g., 95%+_ | User feedback / rating |
| Safety | _0 harmful outputs_ | Automated filter + spot checks |
| Latency | _e.g., < 3s_ | API response time monitoring |
| Cost | _e.g., < $X/month_ | Token usage tracking |

## Test Cases

| Input | Expected Behavior | Result |
|---|---|---|
| Normal input | Correct, relevant output | - |
| Empty input | Graceful fallback | - |
| Very long input | Handles within token limit | - |
| Non-English input | Handles or states limitation | - |
| Adversarial/injection | Refuses safely | - |

## Key Files

| File | Purpose |
|---|---|
| `prompts/[name]-v1.md` | The prompt |
| `src/...` | Feature implementation |
| `tests/...` | Test file |

## Dependencies

- _List AI SDK, other services, etc._

## Notes

_Known limitations, future improvements, edge cases._
