"""
Monday.com <-> Apartment Management Odessa real-time sync.
Pulls data directly from Monday.com GraphQL API and updates local SQLite DB.
"""
import urllib.request
import json
import os
import re

MONDAY_API_URL = 'https://api.monday.com/v2'

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT_DIR, '.env')

def _load_env_var(key):
    val = os.environ.get(key, '')
    if not val and os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line.startswith(key + '='):
                val = line.split('=', 1)[1].strip()
    return val

def get_token():
    return _load_env_var('MONDAY_API_TOKEN')

def get_board_id():
    return _load_env_var('MONDAY_BOARD_ID')

def monday_query(query):
    token = get_token()
    if not token:
        return {'error': 'No Monday.com API token configured'}
    try:
        req = urllib.request.Request(MONDAY_API_URL,
            data=json.dumps({'query': query}).encode(),
            headers={'Authorization': token, 'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {'error': str(e)}

def fetch_board_items():
    board_id = get_board_id()
    if not board_id:
        return []
    query = '''{
        boards(ids: %s) {
            columns { id title }
            items_page(limit: 200) {
                items {
                    id name group { id title }
                    column_values { id text value type }
                    subitems { id name column_values { id text } }
                }
            }
        }
    }''' % board_id
    result = monday_query(query)
    if 'error' in result or 'errors' in result:
        return []
    board = result.get('data', {}).get('boards', [{}])[0]
    # Build column ID -> title map
    col_map = {c['id']: c['title'] for c in board.get('columns', [])}
    items = board.get('items_page', {}).get('items', [])
    # Inject title into column_values
    for item in items:
        for cv in item.get('column_values', []):
            cv['title'] = col_map.get(cv['id'], cv['id'])
    return items

def parse_item(item):
    cols = {}
    for cv in item.get('column_values', []):
        cols[cv['title']] = cv.get('text', '') or ''
        cols[cv['id']] = cv.get('text', '') or ''
        if cv.get('value'):
            try:
                cols[cv['id'] + '_raw'] = json.loads(cv['value'])
            except:
                pass
    rent_str = cols.get('Аренда $', '0').replace(',', '').strip()
    try:
        rent = float(rent_str) if rent_str else 0
    except:
        rent = 0

    meters_str = cols.get('meters', '0').replace(',', '').strip()
    try:
        meters = float(meters_str) if meters_str else 0
    except:
        meters = 0

    status = cols.get('Status', '').strip()
    timeline = cols.get('Timeline of payment', '').strip()

    return {
        'monday_id': item['id'],
        'name': item['name'],
        'group': item.get('group', {}).get('title', ''),
        'status': status,
        'rent': rent,
        'meters': meters,
        'timeline': timeline,
        'internet': cols.get('Internet', ''),
        'code_box': cols.get('Code box', ''),
        'ad_text': cols.get('реклама на аренду квартиры', ''),
        'wifi_paid': cols.get('Wifi paid till', ''),
        'date_start': cols.get('Date start rent', ''),
        'date_finish': cols.get('Date finish rent', '') or cols.get('rent finish', ''),
        'sold': cols.get('Sold!', ''),
        'subitems': item.get('subitems', []),
    }

def _safe_date(v):
    """Parse a date string to YYYY-MM-DD, or return None."""
    if not v:
        return None
    m = re.match(r'(\d{4}-\d{2}-\d{2})', str(v))
    return m.group(1) if m else None


def _find_apt_by_monday_id(mid, query_db):
    """Find apartment whose notes JSON contains the given monday_id."""
    rows = query_db("SELECT * FROM apartments WHERE notes LIKE ?",
                    (f'%"monday_id": "{mid}"%',))
    if not rows:
        # Fallback: broader search (handles different JSON spacing)
        rows = query_db("SELECT * FROM apartments WHERE notes LIKE ?",
                        (f'%{mid}%',))
    return rows[0] if rows else None


def sync_to_db(items=None):
    """
    Non-destructive UPSERT sync from Monday to DB.

    NEVER DELETES:
      - professionals / professional_payments
      - whatsapp_log
      - activity_log
      - notification_prefs
      - app_users / team_members
      - payments (rent payment records)
      - Any lease commission settings (commission_type, commission_value, payment_day)

    Strategy:
      - Apartments: matched by monday_id in notes JSON → UPDATE, or INSERT if new
      - Leases:     find active lease for apt → UPDATE rent + dates only (preserve commission)
                    No active lease → create placeholder tenant + lease
      - Tenants:    never deleted; placeholder "Tenant X" only created if no lease exists

    Pass pre-fetched `items` list to skip Monday API call.
    """
    from src.models import query_db, insert_db, execute_db, init_db

    if items is None:
        items = fetch_board_items()
    if not items:
        return {'synced': 0, 'error': 'No items fetched'}

    # Ensure we have a default property for Tower Chekalov
    existing = query_db(
        "SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
    if not existing:
        init_db()
        existing = query_db(
            "SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
    tower_id = existing['id'] if existing else 1

    def find_property(pattern):
        return query_db(f"SELECT id FROM properties WHERE name LIKE '%{pattern}%'", one=True)

    synced = []
    created = 0
    updated = 0

    for item in items:
        p = parse_item(item)
        mid = str(p['monday_id'])

        # ── Determine property ──────────────────────────────────────────────
        name_lower = p['name'].lower()
        if 'chkalov' in name_lower or 'chekalo' in name_lower:
            prop = query_db(
                "SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
        elif 'pushkin' in name_lower:
            prop = find_property('Pushkin')
        elif 'kanatn' in name_lower:
            prop = find_property('Kanat')
        elif 'voronz' in name_lower or 'voronts' in name_lower:
            prop = find_property('Voronts')
        elif 'arnaut' in name_lower:
            prop = find_property('Arnaut')
        elif 'sofiev' in name_lower:
            prop = find_property('Sofiev')
        elif 'fontank' in name_lower:
            prop = find_property('Fontank')
            if not prop:
                insert_db(
                    "INSERT INTO properties (name, address, type, status, owner_id) VALUES (?, ?, ?, ?, ?)",
                    ("Fontanka Townhouse", "Fontanka, Odessa", "residential", "active", None))
                prop = find_property('Fontank')
        elif 'platinum' in name_lower:
            prop = find_property('Platinum')
            if not prop:
                insert_db(
                    "INSERT INTO properties (name, address, type, status, owner_id) VALUES (?, ?, ?, ?, ?)",
                    ("Parking Platinum", "Odessa", "parking", "active", None))
                prop = find_property('Platinum')
        else:
            prop = None

        property_id = prop['id'] if prop else tower_id

        # ── Extract apartment number ────────────────────────────────────────
        num_match = re.search(r'(\d+(?:/\d+)?)\s*(?:fl|flat|parking|kladovka)', name_lower)
        if num_match:
            apt_number = num_match.group(1)
        else:
            num_match = re.search(r'(?:fl|flat|parking)\s+(\d+)', name_lower)
            apt_number = num_match.group(1) if num_match else p['name'][:20]

        # ── Status mapping ──────────────────────────────────────────────────
        db_status = 'vacant'
        status_lower = p['status'].lower()
        if status_lower == 'rent':
            db_status = 'occupied'
        elif status_lower == 'free':
            db_status = 'vacant'
        elif status_lower == 'stuck':
            db_status = 'maintenance'

        notes_json = json.dumps({
            'monday_id': mid, 'group': p['group'], 'meters': p['meters'],
            'code_box': p['code_box'], 'wifi_paid': p['wifi_paid'],
            'sold': p['sold'], 'timeline': p['timeline'],
        }, ensure_ascii=False)

        # ── UPSERT apartment (never delete) ─────────────────────────────────
        existing_apt = _find_apt_by_monday_id(mid, query_db)
        if existing_apt:
            apt_id = existing_apt['id']
            execute_db(
                "UPDATE apartments SET status=?, monthly_rent=?, notes=? WHERE id=?",
                (db_status, p['rent'], notes_json, apt_id))
            updated += 1
        else:
            apt_id = insert_db(
                "INSERT INTO apartments (property_id, number, status, monthly_rent, currency, notes)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (property_id, apt_number, db_status, p['rent'], 'USD', notes_json))
            created += 1

        # ── UPSERT lease (only update rent + dates; preserve commission) ────
        if db_status == 'occupied' and p['rent'] > 0:
            active_lease = query_db(
                "SELECT * FROM leases WHERE apartment_id=? AND status='active'",
                (apt_id,), one=True)

            if active_lease:
                # Update rent and dates from Monday, but NEVER touch
                # commission_type, commission_value, payment_day, deposit, notes
                date_start  = _safe_date(p['date_start'])
                date_finish = _safe_date(p['date_finish'])
                # Build dynamic UPDATE to avoid PostgreSQL type-inference issues
                # with CASE WHEN NULL IS NOT NULL (psycopg can't infer type of NULL)
                sets = ['rent_amount = ?']
                vals = [p['rent']]
                if date_start:
                    sets.append('start_date = ?')
                    vals.append(date_start)
                if date_finish:
                    sets.append('end_date = ?')
                    vals.append(date_finish)
                vals.append(active_lease['id'])
                execute_db(
                    f"UPDATE leases SET {', '.join(sets)} WHERE id = ?",
                    tuple(vals))
            else:
                # No existing lease — create placeholder tenant + lease
                tenant_name = f"Tenant {p['name']}"
                existing_tenant = query_db(
                    "SELECT id FROM tenants WHERE name=?", (tenant_name,), one=True)
                if existing_tenant:
                    tenant_id = existing_tenant['id']
                else:
                    tenant_id = insert_db(
                        "INSERT INTO tenants (name, language) VALUES (?, ?)",
                        (tenant_name, 'ru'))
                insert_db(
                    "INSERT INTO leases (apartment_id, tenant_id, start_date, end_date,"
                    " rent_amount, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (apt_id, tenant_id,
                     _safe_date(p['date_start']) or '2025-01-01',
                     _safe_date(p['date_finish']),
                     p['rent'], 'active'))

        synced.append({'name': p['name'], 'status': db_status, 'rent': p['rent'], 'id': apt_id})

    return {
        'synced': len(synced),
        'created': created,
        'updated': updated,
        'items': synced,
    }
