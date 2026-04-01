# TASK PIPELINE: Apartment-management-Odessa

> Tasks move through stages in order. Never skip a stage.
> UI must be built and approved before backend work begins.
> Tests are written alongside code, not after.
> Documentation is required before deployment.

---

## Stages

```
⚪ To Do → 🟡 UI First → 🔵 Built (with tests) → 🟢 Tested → 📝 Documented → 🟣 Deployed
```

---

## Pipeline

<!-- DASHBOARD:TASKS:START -->
| Task | Stage | Phase | Blocked By | Notes |
|---|---|---|---|---|
| Design app dashboard UI | 🟡 UI First | 1 | - | index.html with all sections |
| Define database schema | ⚪ To Do | 1 | - | Properties, tenants, leases, payments, meters, tasks, maintenance |
| Property CRUD + cards | ⚪ To Do | 1 | Database schema | 7 properties, 19 units |
| Tenant & lease management | ⚪ To Do | 1 | Property CRUD | 16 active tenants, contract tracking |
| Rent collection tracker | ⚪ To Do | 1 | Tenant management | Monthly tracking, overdue alerts |
| Utility meter readings | ⚪ To Do | 1 | Property CRUD | Log readings, calculate bills, deadline tracking (1st-3rd) |
| Task board | ⚪ To Do | 1 | - | Assign to Alina/Anya, pending/progress/done columns |
| Maintenance work orders | ⚪ To Do | 1 | Property CRUD | Track repairs, warranties, handyman contacts |
| Owner financial reports | ⚪ To Do | 1 | Rent + Utilities | Sam (15-22nd), Natan (10-17th), Kanatna (10-15th) |
| Document storage | ⚪ To Do | 1 | Property CRUD | Upload contracts, photos, warranties per property |
| Flask API backend | ⚪ To Do | 1 | Database schema | REST API for all CRUD operations |
| Connect frontend to API | ⚪ To Do | 1 | Flask API + UI | Wire up dashboard with real data |
| Mobile responsive polish | ⚪ To Do | 1 | Frontend complete | PWA manifest, touch-friendly |
| Deploy MVP | ⚪ To Do | 1 | All Phase 1 tasks | VPS + GitHub Pages |
| Multi-language UI | ⚪ To Do | 2 | MVP deployed | RU, HE (RTL), EN |
| Automated notifications | ⚪ To Do | 2 | MVP deployed | Telegram/WhatsApp bots for reminders |
| Role-based access | ⚪ To Do | 2 | MVP deployed | Owner vs manager permissions |
<!-- DASHBOARD:TASKS:END -->

---

## Completed (Archive)

> Move tasks here once 🟣 Deployed and stable for a week.

| Task | Phase | Completed | Notes |
|---|---|---|---|
| Project scaffolding | 0 | 2026-04-01 | ProjectOS v3.3.0 template |
| GitHub repo setup | 0 | 2026-04-01 | SSH keys, remote configured, pushed |
| Requirements gathering | 0 | 2026-04-01 | Transcripts analyzed, task matrix reviewed |
