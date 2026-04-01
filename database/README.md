# Database

## Structure

```
database/
├── schema/       ← Schema definitions (SQL, Prisma, Drizzle, etc.)
├── migrations/   ← Migration files (ordered chronologically)
├── seeds/        ← Seed data for development and testing
└── README.md     ← You are here
```

## Setup

```bash
# TODO: Add database setup commands
make setup
```

## Schema Diagram

```
TODO: Add schema diagram once tables are defined
```

## Conventions

- Migrations are numbered: `001_create_users.sql`, `002_add_posts.sql`
- Never edit a migration that's been pushed — create a new one
- Seed data should be idempotent (safe to run multiple times)
- Document schema changes in the session log
