# API: [ENDPOINT OR GROUP NAME]

> Created: YYYY-MM-DD | Status: [Active / Deprecated]

## Overview

[Brief description of what this API endpoint or group handles]

## Endpoints

### `METHOD /path`

**Description:** [what it does]

**Auth required:** [yes/no — what type]

**Request:**
```json
{
  "field": "type — description"
}
```

**Response (200):**
```json
{
  "field": "type — description"
}
```

**Error responses:**
| Status | Reason |
|---|---|
| 400 | [when this happens] |
| 401 | [when this happens] |
| 404 | [when this happens] |

**Example:**
```bash
curl -X METHOD https://api.example.com/path \
  -H "Authorization: Bearer TOKEN" \
  -d '{"field": "value"}'
```

## Key Files

| File | Purpose |
|---|---|
| `src/...` | [route handler] |
| `src/...` | [service logic] |
| `tests/...` | [test file] |

## Notes

[Rate limits, caching, or anything else to know]
