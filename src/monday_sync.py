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
    req = urllib.request.Request(MONDAY_API_URL,
        data=json.dumps({'query': query}).encode(),
        headers={'Authorization': token, 'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

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

def sync_to_db():
    from src.models import query_db, insert_db, execute_db, init_db
    items = fetch_board_items()
    if not items:
        return {'synced': 0, 'error': 'No items fetched'}

    # Delete in FK-safe order (children before parents)
    execute_db("DELETE FROM payments")
    execute_db("DELETE FROM leases")
    execute_db("DELETE FROM tenants")
    execute_db("DELETE FROM meter_readings")
    execute_db("DELETE FROM utility_bills")
    execute_db("DELETE FROM warranties")
    execute_db("DELETE FROM maintenance_orders")
    execute_db("DELETE FROM documents WHERE apartment_id IS NOT NULL")
    execute_db("DELETE FROM apartments")

    # Ensure we have a default property for Tower Chekalov
    existing = query_db("SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
    if not existing:
        init_db()
        existing = query_db("SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
    tower_id = existing['id'] if existing else 1

    def find_property(pattern):
        return query_db(f"SELECT id FROM properties WHERE name LIKE '%{pattern}%'", one=True)

    synced = []
    for item in items:
        p = parse_item(item)

        # Determine property_id based on name
        name_lower = p['name'].lower()
        if 'chkalov' in name_lower or 'chekalo' in name_lower:
            prop = query_db("SELECT id FROM properties WHERE name LIKE '%Chekalov%' OR name LIKE '%Chkalov%'", one=True)
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
                insert_db("INSERT INTO properties (name, address, type, status, owner_id) VALUES (?, ?, ?, ?, ?)",
                    ("Fontanka Townhouse", "Fontanka, Odessa", "residential", "active", None))
                prop = find_property('Fontank')
        elif 'platinum' in name_lower:
            prop = find_property('Platinum')
            if not prop:
                insert_db("INSERT INTO properties (name, address, type, status, owner_id) VALUES (?, ?, ?, ?, ?)",
                    ("Parking Platinum", "Odessa", "parking", "active", None))
                prop = find_property('Platinum')
        else:
            prop = None

        property_id = prop['id'] if prop else tower_id

        # Extract apartment number from name
        num_match = re.search(r'(\d+(?:/\d+)?)\s*(?:fl|flat|parking|kladovka)', name_lower)
        if num_match:
            apt_number = num_match.group(1)
        else:
            num_match = re.search(r'(?:fl|flat|parking)\s+(\d+)', name_lower)
            apt_number = num_match.group(1) if num_match else p['name'][:20]

        # Status mapping
        db_status = 'vacant'
        if p['status'].lower() == 'rent':
            db_status = 'occupied'
        elif p['status'].lower() == 'free':
            db_status = 'vacant'
        elif p['status'].lower() == 'stuck':
            db_status = 'maintenance'

        # Insert apartment
        apt_id = insert_db(
            "INSERT INTO apartments (property_id, number, status, monthly_rent, currency, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (property_id, apt_number, db_status, p['rent'], 'USD',
             json.dumps({'monday_id': p['monday_id'], 'group': p['group'], 'meters': p['meters'],
                         'code_box': p['code_box'], 'wifi_paid': p['wifi_paid'],
                         'sold': p['sold'], 'timeline': p['timeline']}, ensure_ascii=False)))

        # If occupied, create a placeholder tenant + lease
        if db_status == 'occupied' and p['rent'] > 0:
            tenant_name = f"Tenant {p['name']}"
            tenant_id = insert_db("INSERT INTO tenants (name, language) VALUES (?, ?)", (tenant_name, 'ru'))
            def _safe_date(v, default=None):
                if not v:
                    return default
                m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(v))
                return m.group(0) if m else default
            insert_db(
                "INSERT INTO leases (apartment_id, tenant_id, start_date, end_date, rent_amount, status) VALUES (?, ?, ?, ?, ?, ?)",
                (apt_id, tenant_id, _safe_date(p['date_start'], '2025-01-01'), _safe_date(p['date_finish']), p['rent'], 'active'))

        synced.append({'name': p['name'], 'status': db_status, 'rent': p['rent']})
    return {'synced': len(synced), 'items': synced}
