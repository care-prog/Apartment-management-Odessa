# AI Documentation

This directory contains documentation for all AI-powered features and agents.

## Templates

- `AI_FEATURE_TEMPLATE.md` — For any feature that calls an AI model (generation, classification, extraction, etc.)
- `AGENT_TEMPLATE.md` — For autonomous agents with tool use, multi-step reasoning, or memory

## Rules

1. Every AI feature gets one doc here before marking as 📝 Documented
2. Every agent gets one doc here using the agent template
3. Document model choice with justification (see CLAUDE.md Rule 12)
4. Link to the corresponding prompt file in `prompts/`
5. Include evaluation criteria — how do we know it's working?
6. Keep docs updated when prompts change
