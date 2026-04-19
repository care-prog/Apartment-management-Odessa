"""DB layer with dual SQLite/PostgreSQL support.

If DATABASE_URL env var is set → use PostgreSQL.
Otherwise → use local SQLite (for development).

The wrapper translates SQLite-style ? placeholders and INSERT OR IGNORE syntax
so all existing route code works unchanged on both backends.
"""
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'apartment_mgmt.db')
SCHEMA_SQLITE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema', '001_initial.sql')
SCHEMA_PG = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema', '001_initial_pg.sql')

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_PG = bool(DATABASE_URL)

if USE_PG:
    import psycopg
    from psycopg.rows import dict_row


def _translate(query: str) -> str:
    """Translate SQLite-flavored SQL to PostgreSQL when needed."""
    if not USE_PG:
        return query
    # 1) Escape literal % (e.g. in LIKE '%foo%') so psycopg doesn't treat it as a format spec
    out = query.replace('%', '%%')
    # 2) ? placeholders → %s
    out = out.replace('?', '%s')
    # 3) INSERT OR IGNORE INTO table → INSERT INTO table ... ON CONFLICT DO NOTHING
    if re.search(r'INSERT\s+OR\s+IGNORE\s+INTO', out, re.IGNORECASE):
        out = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', out, flags=re.IGNORECASE)
        if 'ON CONFLICT' not in out.upper():
            out = out.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return out


def get_db():
    if USE_PG:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    schema_path = SCHEMA_PG if USE_PG else SCHEMA_SQLITE
    if not USE_PG:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    with open(schema_path, 'r') as f:
        sql = f.read()
    if USE_PG:
        with db.cursor() as cur:
            cur.execute(sql)
        db.commit()
    else:
        db.executescript(sql)
    db.close()


def query_db(query, args=(), one=False):
    q = _translate(query)
    db = get_db()
    if USE_PG:
        with db.cursor() as cur:
            cur.execute(q, args)
            rv = cur.fetchall() if cur.description else []
    else:
        cur = db.execute(q, args)
        rv = [dict(row) for row in cur.fetchall()]
    db.close()
    return (rv[0] if rv else None) if one else rv


def insert_db(query, args=()):
    q = _translate(query)
    db = get_db()
    if USE_PG:
        # Append RETURNING id if not present, so we can get lastrowid equivalent
        if 'RETURNING' not in q.upper():
            q = q.rstrip().rstrip(';') + ' RETURNING id'
        last_id = None
        with db.cursor() as cur:
            cur.execute(q, args)
            try:
                row = cur.fetchone()
                if row:
                    last_id = row.get('id') if isinstance(row, dict) else row[0]
            except psycopg.ProgrammingError:
                # ON CONFLICT DO NOTHING with no row inserted
                last_id = None
        db.commit()
    else:
        cur = db.execute(q, args)
        db.commit()
        last_id = cur.lastrowid
    db.close()
    return last_id


def execute_db(query, args=()):
    q = _translate(query)
    db = get_db()
    if USE_PG:
        with db.cursor() as cur:
            cur.execute(q, args)
        db.commit()
    else:
        db.execute(q, args)
        db.commit()
    db.close()
