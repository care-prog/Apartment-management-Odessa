"""DB layer with dual SQLite/PostgreSQL support.

If DATABASE_URL env var is set → use PostgreSQL.
Otherwise → use local SQLite (for development).

The wrapper translates SQLite-style ? placeholders and INSERT OR IGNORE syntax
so all existing route code works unchanged on both backends.
"""
import os
import re
import sqlite3
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'apartment_mgmt.db')
SCHEMA_SQLITE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema', '001_initial.sql')
SCHEMA_PG = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema', '001_initial_pg.sql')

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_PG = bool(DATABASE_URL)

if USE_PG:
    import psycopg
    from psycopg.rows import dict_row


def _serialize_row(row):
    """Convert datetime/date objects in a row dict to ISO strings."""
    if row is None:
        return None
    return {k: v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v
            for k, v in row.items()}


def month_str(col: str) -> str:
    """Returns SQL to format a date column as 'YYYY-MM'. DB-agnostic."""
    if USE_PG:
        return f"TO_CHAR({col}, 'YYYY-MM')"
    return f"strftime('%Y-%m', {col})"


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
        # connect_timeout=10 prevents hanging indefinitely on cold PG connections
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False,
                               connect_timeout=10)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def _pg_run(sql, args=()):
    """Run a single PG migration statement, ignoring errors (idempotent)."""
    try:
        execute_db(sql, args)
    except Exception as e:
        print(f'[safe_migrate PG] ignored: {e!r} — SQL: {sql[:80]}')


def safe_migrate():
    """Idempotent migrations — add missing columns and tables to existing DBs."""
    if USE_PG:
        _pg_run("ALTER TABLE office_expenses ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'")
        _pg_run("ALTER TABLE owners ADD COLUMN IF NOT EXISTS phone TEXT")
        _pg_run("ALTER TABLE owners ADD COLUMN IF NOT EXISTS email TEXT")
        _pg_run("ALTER TABLE owners ADD COLUMN IF NOT EXISTS bank_details TEXT")
        # Per-apartment owner: each apartment can belong to a different owner
        # (e.g. Tower Chekalov has multiple investors, each owning different units)
        _pg_run("ALTER TABLE apartments ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL")
        _pg_run("""UPDATE apartments SET owner_id = (
            SELECT owner_id FROM properties WHERE properties.id = apartments.property_id
        ) WHERE owner_id IS NULL""")
        _pg_run("""CREATE TABLE IF NOT EXISTS cash_transactions (
            id SERIAL PRIMARY KEY, type TEXT NOT NULL DEFAULT 'expense',
            amount DOUBLE PRECISION NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
            category TEXT DEFAULT 'general', description TEXT, transaction_date DATE,
            apartment_id INTEGER REFERENCES apartments(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS commission_overrides (
            monday_id TEXT PRIMARY KEY, commission_type TEXT NOT NULL DEFAULT 'percent',
            commission_value DOUBLE PRECISION NOT NULL DEFAULT 10,
            notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY, action TEXT NOT NULL, entity_type TEXT NOT NULL,
            entity_id TEXT, description TEXT, before_data TEXT,
            user_role TEXT DEFAULT 'owner', ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'office', permissions TEXT NOT NULL DEFAULT '{}',
            property_ids TEXT NOT NULL DEFAULT '[]', is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT 'Owner'")
        _pg_run("""CREATE TABLE IF NOT EXISTS professionals (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL, phone TEXT, phone_2 TEXT,
            messenger TEXT DEFAULT 'Viber', category TEXT DEFAULT 'Other', notes TEXT,
            apartments_worked TEXT, total_paid DOUBLE PRECISION DEFAULT 0,
            rating INTEGER DEFAULT 5, is_active INTEGER DEFAULT 1, monday_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS professional_payments (
            id SERIAL PRIMARY KEY,
            professional_id INTEGER REFERENCES professionals(id) ON DELETE CASCADE,
            amount DOUBLE PRECISION NOT NULL, currency TEXT DEFAULT 'USD',
            description TEXT, payment_date DATE,
            task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("ALTER TABLE maintenance_orders ADD COLUMN IF NOT EXISTS paid_by TEXT DEFAULT 'office'")
        _pg_run("ALTER TABLE maintenance_orders ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'")
        _pg_run("ALTER TABLE leases ADD COLUMN IF NOT EXISTS commission_type TEXT DEFAULT 'percent'")
        _pg_run("ALTER TABLE leases ADD COLUMN IF NOT EXISTS commission_value DOUBLE PRECISION DEFAULT 0")
        _pg_run("ALTER TABLE leases ADD COLUMN IF NOT EXISTS payment_day INTEGER DEFAULT 1")
        _pg_run("""CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY, value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS whatsapp_log (
            id SERIAL PRIMARY KEY,
            direction TEXT NOT NULL DEFAULT 'in',
            from_phone TEXT, to_phone TEXT,
            sender_name TEXT, sender_role TEXT,
            body TEXT, status TEXT DEFAULT 'ok',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        _pg_run("""CREATE TABLE IF NOT EXISTS team_members (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL, phone TEXT UNIQUE,
            role TEXT DEFAULT 'manager', language TEXT DEFAULT 'ru',
            access_level TEXT DEFAULT 'full',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    else:
        try: execute_db("ALTER TABLE office_expenses ADD COLUMN currency TEXT DEFAULT 'USD'")
        except: pass
        try: execute_db("ALTER TABLE owners ADD COLUMN phone TEXT")
        except: pass
        try: execute_db("ALTER TABLE owners ADD COLUMN email TEXT")
        except: pass
        try: execute_db("ALTER TABLE owners ADD COLUMN bank_details TEXT")
        except: pass
        try: execute_db("ALTER TABLE apartments ADD COLUMN owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL")
        except: pass
        execute_db("""UPDATE apartments SET owner_id = (
            SELECT owner_id FROM properties WHERE properties.id = apartments.property_id
        ) WHERE owner_id IS NULL""")
        execute_db("""CREATE TABLE IF NOT EXISTS cash_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL DEFAULT 'expense',
            amount REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
            category TEXT DEFAULT 'general', description TEXT, transaction_date DATE,
            apartment_id INTEGER REFERENCES apartments(id) ON DELETE SET NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS commission_overrides (
            monday_id TEXT PRIMARY KEY, commission_type TEXT NOT NULL DEFAULT 'percent',
            commission_value REAL NOT NULL DEFAULT 10, notes TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id TEXT, description TEXT,
            before_data TEXT, user_role TEXT DEFAULT 'owner', ip_address TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'office', permissions TEXT NOT NULL DEFAULT '{}',
            property_ids TEXT NOT NULL DEFAULT '[]', is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        try: execute_db("ALTER TABLE activity_log ADD COLUMN user_name TEXT DEFAULT 'Owner'")
        except: pass
        execute_db("""CREATE TABLE IF NOT EXISTS professionals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            phone TEXT, phone_2 TEXT, messenger TEXT DEFAULT 'Viber',
            category TEXT DEFAULT 'Other', notes TEXT, apartments_worked TEXT,
            total_paid REAL DEFAULT 0, rating INTEGER DEFAULT 5,
            is_active INTEGER DEFAULT 1, monday_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS professional_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professional_id INTEGER REFERENCES professionals(id) ON DELETE CASCADE,
            amount REAL NOT NULL, currency TEXT DEFAULT 'USD',
            description TEXT, payment_date DATE,
            task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        try: execute_db("ALTER TABLE maintenance_orders ADD COLUMN paid_by TEXT DEFAULT 'office'")
        except: pass
        try: execute_db("ALTER TABLE maintenance_orders ADD COLUMN currency TEXT DEFAULT 'USD'")
        except: pass
        try: execute_db("ALTER TABLE leases ADD COLUMN commission_type TEXT DEFAULT 'percent'")
        except: pass
        try: execute_db("ALTER TABLE leases ADD COLUMN commission_value REAL DEFAULT 0")
        except: pass
        try: execute_db("ALTER TABLE leases ADD COLUMN payment_day INTEGER DEFAULT 1")
        except: pass
        execute_db("""CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY, value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS whatsapp_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL DEFAULT 'in',
            from_phone TEXT, to_phone TEXT,
            sender_name TEXT, sender_role TEXT,
            body TEXT, status TEXT DEFAULT 'ok',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        execute_db("""CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE,
            role TEXT DEFAULT 'manager', language TEXT DEFAULT 'ru',
            access_level TEXT DEFAULT 'full',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")


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
            rv = [_serialize_row(r) for r in (cur.fetchall() if cur.description else [])]
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


def get_setting(key, default=None):
    """Read a value from system_settings table. Returns default if not found."""
    try:
        row = query_db('SELECT value FROM system_settings WHERE key = ?', (key,), one=True)
        return row['value'] if row else default
    except Exception:
        return default


def set_setting(key, value):
    """Upsert a key-value pair in system_settings."""
    try:
        existing = query_db('SELECT key FROM system_settings WHERE key = ?', (key,), one=True)
        if existing:
            execute_db('UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                       (value, key))
        else:
            execute_db('INSERT INTO system_settings (key, value) VALUES (?, ?)', (key, value))
    except Exception:
        pass
