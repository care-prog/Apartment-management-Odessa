# [Agent Name] — Agent Architecture Doc

> One doc per AI agent. Covers architecture, tool usage, memory, and evaluation.

## Status: ⚪ Draft / 🟡 In Development / 🟢 Production

## What It Does

_1-2 sentences. What task does this agent perform autonomously?_

## Architecture

### Overview
```
[Trigger] → [Agent Loop] → [Output/Action]
                ↕
          [Tools / Memory]
```

### Model & Cost

| Field | Value |
|---|---|
| Model | haiku / sonnet / opus |
| Why this model | _Justification_ |
| Avg turns per task | - |
| Est. cost/task | - |
| Monthly budget | - |

### Agent Loop

1. Receive task/input
2. Plan approach
3. Execute step (call tool or reason)
4. Evaluate result
5. Repeat 3-4 until done or max turns reached
6. Return final output

**Max turns:** _e.g., 10_
**Timeout:** _e.g., 60s_

## Tools

| Tool | Purpose | When Used |
|---|---|---|
| `tool_name` | What it does | Trigger condition |

### Tool Schemas
```json
{
  "name": "tool_name",
  "description": "What it does",
  "input_schema": {
    "type": "object",
    "properties": {}
  }
}
```

## Memory & Context

- **Context window strategy:** How context is managed (full history, sliding window, summary)
- **Persistent memory:** What is stored between sessions (if any)
- **Context injection:** What background info is always provided

## System Prompt

```
[The agent's system prompt — or reference to prompts/ file]
```

## Error Handling

| Scenario | Handling |
|---|---|
| Tool call fails | Retry once, then report to user |
| Max turns exceeded | Return partial result with explanation |
| Rate limit | Queue and retry with backoff |
| Hallucinated tool | Validate tool names before execution |
| Infinite loop | Turn counter + diversity check |

## Guardrails

- **Input validation:** What inputs are accepted/rejected
- **Output validation:** What outputs are checked before returning
- **Action limits:** What the agent is NOT allowed to do
- **Human-in-the-loop:** When does the agent pause for human approval

## Evaluation

| Criteria | Target | How Measured |
|---|---|---|
| Task completion | _e.g., 85%+_ | Success rate over N tasks |
| Accuracy | _e.g., 90%+_ | Manual review |
| Efficiency | _e.g., < 5 turns avg_ | Turn count tracking |
| Cost/task | _e.g., < $0.10_ | Token usage |
| Safety | _0 unauthorized actions_ | Audit log review |

## Key Files

| File | Purpose |
|---|---|
| `prompts/[agent]-system-v1.md` | System prompt |
| `src/agents/...` | Agent implementation |
| `src/tools/...` | Tool implementations |
| `tests/agents/...` | Agent test suite |

## Notes

_Known limitations, planned improvements, edge cases._
