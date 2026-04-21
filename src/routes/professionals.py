"""Professionals module — contacts directory for tradespeople, cleaners, etc."""
import os
import requests
from flask import Blueprint, jsonify, request
from src.models import query_db, insert_db, execute_db

bp = Blueprint('professionals', __name__)

MONDAY_API_URL = 'https://api.monday.com/v2'
MONDAY_BOARD_ID = 5261090733


def detect_category(name):
    n = name.lower()
    cats = [
        ('Tile Work', ['plitka', 'плитк']),
        ('Doors', ['door', 'двер']),
        ('Construction', ['prorab', 'прораб', 'restavr', 'remont']),
        ('Plumbing', ['santehnik', 'сантехник', 'kotel', 'котел', 'filter', 'фильтр', 'battery', 'батар']),
        ('Electrical', ['electric', 'электрик']),
        ('Cleaning', ['cleaning', 'уборщ', 'уборка']),
        ('Realtor', ['rieltor', 'риелтор', 'риэлтор', 'realtor', 'makler']),
        ('Legal', ['юрист', 'lawyer']),
        ('Locksmith', ['взлом', 'locksmith']),
        ('Fire Safety', ['пожарник', 'fire']),
        ('Design', ['дизайнер', 'design']),
        ('Furniture', ['мебель', 'furniture', 'mebel', 'sofa']),
        ('Windows/Glass', ['glass', 'окна', 'window']),
        ('A/C', ['condition', 'кондиц']),
        ('Laundry', ['стирк', 'textile', 'bedline']),
        ('Painting', ['paint', 'покрас', 'маляр']),
        ('IT/Tech', ['it yura', 'camera', 'tech']),
        ('Materials/Supply', ['material', 'supply', 'account', 'ламинат']),
        ('Neighbor Contact', ['neighbour', 'neighbor', 'сосед']),
        ('Utilities', ['water', 'водоканал', 'нафто']),
        ('Internet/TV', ['internet', 'интернет', 'соборк']),
        ('Documents/Printing', ['copycenter', 'copy', 'перевод', 'translation']),
        ('Photography', ['photo', 'фото']),
        ('Building Admin', ['reception', 'abon']),
    ]
    for cat, keywords in cats:
        if any(k in n for k in keywords):
            return cat
    return 'Other'


def _pro_row(row):
    """Ensure all fields are present and typed correctly."""
    if not row:
        return row
    row['total_paid'] = float(row.get('total_paid') or 0)
    row['rating'] = int(row.get('rating') or 5)
    row['is_active'] = int(row.get('is_active') or 1)
    return row


# ── List all professionals ──────────────────────────────────────────────────
@bp.route('/api/professionals', methods=['GET'])
def list_professionals():
    category = request.args.get('category', '').strip()
    search = request.args.get('search', '').strip()

    base = """
        SELECT p.*,
               COALESCE(SUM(pp.amount), 0) AS total_paid_computed
        FROM professionals p
        LEFT JOIN professional_payments pp ON pp.professional_id = p.id
        WHERE 1=1
    """
    args = []

    if category:
        base += ' AND p.category = ?'
        args.append(category)
    if search:
        base += ' AND (p.name LIKE ? OR p.notes LIKE ? OR p.apartments_worked LIKE ?)'
        like = '%' + search + '%'
        args.extend([like, like, like])

    base += ' GROUP BY p.id ORDER BY p.name'
    rows = query_db(base, args)
    result = []
    for r in rows:
        r = dict(r)
        # Prefer live-computed total over stored column
        r['total_paid'] = float(r.pop('total_paid_computed', 0) or 0)
        result.append(_pro_row(r))
    return jsonify(result)


# ── Create professional ─────────────────────────────────────────────────────
@bp.route('/api/professionals', methods=['POST'])
def create_professional():
    d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    pid = insert_db(
        'INSERT INTO professionals (name, phone, phone_2, messenger, category, notes, apartments_worked, rating, monday_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (name, d.get('phone', ''), d.get('phone_2', ''), d.get('messenger', 'Viber'),
         d.get('category', 'Other'), d.get('notes', ''), d.get('apartments_worked', ''),
         int(d.get('rating', 5)), d.get('monday_id'))
    )
    row = query_db('SELECT * FROM professionals WHERE id = ?', (pid,), one=True)
    return jsonify(_pro_row(dict(row))), 201


# ── Get one professional with payments ─────────────────────────────────────
@bp.route('/api/professionals/<int:pid>', methods=['GET'])
def get_professional(pid):
    row = query_db('SELECT * FROM professionals WHERE id = ?', (pid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    data = _pro_row(dict(row))
    payments = query_db(
        'SELECT * FROM professional_payments WHERE professional_id = ? ORDER BY payment_date DESC, id DESC',
        (pid,)
    )
    data['payments'] = [dict(p) for p in payments]
    data['total_paid'] = sum(float(p['amount']) for p in data['payments'])
    return jsonify(data)


# ── Update professional ─────────────────────────────────────────────────────
@bp.route('/api/professionals/<int:pid>', methods=['PUT'])
def update_professional(pid):
    row = query_db('SELECT id FROM professionals WHERE id = ?', (pid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    d = request.json or {}
    execute_db(
        '''UPDATE professionals SET name=?, phone=?, phone_2=?, messenger=?,
           category=?, notes=?, apartments_worked=?, rating=? WHERE id=?''',
        (d.get('name', ''), d.get('phone', ''), d.get('phone_2', ''),
         d.get('messenger', 'Viber'), d.get('category', 'Other'),
         d.get('notes', ''), d.get('apartments_worked', ''),
         int(d.get('rating', 5)), pid)
    )
    updated = query_db('SELECT * FROM professionals WHERE id = ?', (pid,), one=True)
    return jsonify(_pro_row(dict(updated)))


# ── Delete professional ─────────────────────────────────────────────────────
@bp.route('/api/professionals/<int:pid>', methods=['DELETE'])
def delete_professional(pid):
    execute_db('DELETE FROM professionals WHERE id = ?', (pid,))
    return jsonify({'ok': True})


# ── Add payment ─────────────────────────────────────────────────────────────
@bp.route('/api/professionals/<int:pid>/payments', methods=['POST'])
def add_payment(pid):
    row = query_db('SELECT id FROM professionals WHERE id = ?', (pid,), one=True)
    if not row:
        return jsonify({'error': 'professional not found'}), 404
    d = request.json or {}
    amount = d.get('amount')
    if amount is None:
        return jsonify({'error': 'amount required'}), 400
    pay_id = insert_db(
        'INSERT INTO professional_payments (professional_id, amount, currency, description, payment_date, task_id) VALUES (?, ?, ?, ?, ?, ?)',
        (pid, float(amount), d.get('currency', 'USD'), d.get('description', ''),
         d.get('payment_date'), d.get('task_id'))
    )
    pay = query_db('SELECT * FROM professional_payments WHERE id = ?', (pay_id,), one=True)
    return jsonify(dict(pay)), 201


# ── Delete payment ──────────────────────────────────────────────────────────
@bp.route('/api/professional-payments/<int:payid>', methods=['DELETE'])
def delete_payment(payid):
    execute_db('DELETE FROM professional_payments WHERE id = ?', (payid,))
    return jsonify({'ok': True})


# ── Sync from Monday.com ────────────────────────────────────────────────────
def run_professionals_sync():
    """
    Core sync logic — callable directly from the scheduler (no HTTP context needed).
    Returns dict: {ok, imported, skipped, total, error?}
    """
    token = os.environ.get('MONDAY_API_TOKEN', '').strip()
    if not token:
        return {'error': 'MONDAY_API_TOKEN not set'}

    q = ('{ boards(ids:[' + str(MONDAY_BOARD_ID) + ']){ '
         'items_page(limit:100){ items{ id name '
         'column_values{ id text } } } } }')
    try:
        resp = requests.post(
            MONDAY_API_URL,
            json={'query': q},
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {'error': str(e)}

    boards = (data.get('data') or {}).get('boards') or []
    if not boards:
        return {'error': 'No boards returned'}

    items = boards[0].get('items_page', {}).get('items', [])
    imported = 0
    skipped = 0
    for item in items:
        mid = str(item['id'])
        name = item['name'].strip()
        if not name:
            continue
        existing = query_db('SELECT id FROM professionals WHERE monday_id = ?', (mid,), one=True)
        if existing:
            skipped += 1
            continue
        cols = {cv['id']: cv['text'] for cv in item.get('column_values', [])}
        phone = cols.get('phone', '') or ''
        phone_2 = cols.get('phone_1', '') or ''
        messenger = cols.get('label7', '') or 'Viber'
        if messenger not in ('WhatsApp', 'Viber', 'Telegram', 'None'):
            messenger = 'Viber'
        notes = cols.get('text', '') or ''
        category = detect_category(name)
        insert_db(
            'INSERT OR IGNORE INTO professionals (name, phone, phone_2, messenger, category, notes, monday_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (name, phone, phone_2, messenger, category, notes, mid)
        )
        imported += 1

    return {'ok': True, 'imported': imported, 'skipped': skipped, 'total': len(items),
            'message': f'Added {imported} new. Skipped {skipped} existing.'}


@bp.route('/api/professionals/sync-monday', methods=['POST'])
def sync_monday():
    result = run_professionals_sync()
    if result.get('error'):
        return jsonify(result), 500
    return jsonify(result)
