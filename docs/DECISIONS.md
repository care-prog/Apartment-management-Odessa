# Architectural Decisions

> Every significant technical decision is logged here with context, options, and rationale.
> Newest entries at the top. See CLAUDE.md Rule 11 for what qualifies.

<!-- DASHBOARD:DECISIONS:START -->

### 1. Platform: Web + PWA (not native mobile)
**Context:** David manages remotely, managers use phones in the field.
**Options:** (a) Web only, (b) Web + native mobile, (c) Web + PWA
**Decision:** Web + PWA — responsive web app that's installable on phones. No app store needed, single codebase.
**Rationale:** Fastest to build, works on all devices, no deployment friction.

### 2. Backend: Flask + SQLite (not Node.js, not Django)
**Context:** Need a lightweight API server for CRUD operations.
**Options:** (a) Node.js/Express, (b) Django, (c) Flask + SQLite
**Decision:** Flask + SQLite — minimal setup, Python already available on system.
**Rationale:** SQLite requires no server, Flask is lightweight. Can migrate to PostgreSQL later if needed. Django is overkill for MVP.

### 3. Frontend: Vanilla HTML/CSS/JS + Alpine.js (not React/Vue)
**Context:** Dashboard UI needs to be responsive and interactive.
**Options:** (a) React, (b) Vue, (c) Vanilla + Alpine.js
**Decision:** Vanilla HTML/CSS with Alpine.js for reactivity.
**Rationale:** No build step, fastest iteration, builds on existing ProjectOS template. Can add framework later if complexity grows.

### 4. All-in-one dashboard (not module-by-module phasing)
**Context:** David needs visibility across all operations immediately.
**Options:** (a) Build one module at a time, (b) All-in-one with basic functionality
**Decision:** All-in-one dashboard with basic CRUD across all areas.
**Rationale:** David confirmed this approach. Better to have shallow coverage across everything than deep coverage of one area while blind to others.

<!-- DASHBOARD:DECISIONS:END -->
