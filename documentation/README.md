# Documentation

> Every feature, automation, and API endpoint gets its own doc before it can be marked as 🟣 Deployed.

## Structure

```
documentation/
├── features/       ← One doc per feature (use FEATURE_TEMPLATE.md)
├── automations/    ← One doc per automation or workflow
└── api/            ← One doc per API endpoint or group
```

## Rules

- A task cannot move to 📝 Documented (and then 🟣 Deployed) without a doc in the appropriate folder
- Name files clearly: `user-authentication.md`, `invoice-generator.md`, `stripe-webhook.md`
- Keep docs updated when the code changes — stale docs are worse than no docs
- The first feature documented becomes the reference pattern for all future docs
