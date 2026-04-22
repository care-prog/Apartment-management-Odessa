"""WA Contacts Registry — internal registry of WhatsApp-enabled contacts.
Each contact stores user_fields (JSON) used as placeholders in templates.
"""
import json
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('wa_contacts', __name__)


def _build_user_fields(entity_type, entity_id):
    """Build user_fields JSON from entity data."""
    fields = {}
    if entity_type == 'tenant':
        row = query_db("""
            SELECT t.name, t.phone, t.email, t.language,
                   a.number as apartment, p.name as building,
                   l.rent_amount, l.currency, l.end_date
            FROM tenants t
            LEFT JOIN leases l ON l.tenant_id = t.id AND l.status = 'active'
            LEFT JOIN apartments a ON l.apartment_id = a.id
            LEFT JOIN properties p ON a.property_id = p.id
            WHERE t.id = ?
        """, (entity_id,), one=True)
        if row:
            fields = {
                'name': row.get('name', ''),
                'phone': row.get('phone', ''),
                'email': row.get('email', ''),
                'language': row.get('language', 'ru'),
                'apartment': str(row.get('apartment', '')),
                'building': row.get('building', ''),
                'rent': str(row.get('rent_amount', '')),
                'currency': row.get('currency', 'USD'),
                'lease_end': row.get('end_date', ''),
            }

    elif entity_type == 'professional':
        row = query_db('SELECT * FROM professionals WHERE id = ?', (entity_id,), one=True)
        if row:
            fields = {
                'name': row.get('name', ''),
                'phone': row.get('phone', ''),
                'phone_2': row.get('phone_2', ''),
                'category': row.get('category', ''),
                'messenger': row.get('messenger', 'Viber'),
                'language': 'ru',
            }

    elif entity_type == 'owner':
        row = query_db('SELECT * FROM owners WHERE id = ?', (entity_id,), one=True)
        if row:
            fields = {
                'name': row.get('name', ''),
                'phone': row.get('phone') or row.get('contact', ''),
                'email': row.get('email', ''),
                'language': 'ru',
            }

    elif entity_type == 'team':
        row = query_db('SELECT * FROM team_members WHERE id = ?', (entity_id,), one=True)
        if row:
            fields = {
                'name': row.get('name', ''),
                'phone': row.get('phone', ''),
                'role': row.get('role', ''),
                'language': row.get('language', 'ru'),
            }

    return fields


def _get_entity_phone(entity_type, entity_id):
    """Return the primary phone for an entity."""
    if entity_type == 'tenant':
        row = query_db('SELECT phone FROM tenants WHERE id = ?', (entity_id,), one=True)
    elif entity_type == 'professional':
        row = query_db('SELECT phone FROM professionals WHERE id = ?', (entity_id,), one=True)
    elif entity_type == 'owner':
        row = query_db('SELECT COALESCE(phone, contact) as phone FROM owners WHERE id = ?', (entity_id,), one=True)
    elif entity_type == 'team':
        row = query_db('SELECT phone FROM team_members WHERE id = ?', (entity_id,), one=True)
    else:
        return None
    return (row or {}).get('phone')


# ── List all WA contacts ────────────────────────────────────────────────────
@bp.route('/api/wa/contacts', methods=['GET'])
def list_wa_contacts():
    entity_type = request.args.get('entity_type', '')
    search = request.args.get('search', '').strip()
    query = 'SELECT * FROM wa_contacts WHERE 1=1'
    args = []
    if entity_type:
        query += ' AND entity_type = ?'
        args.append(entity_type)
    if search:
        query += ' AND (name LIKE ? OR phone LIKE ?)'
        like = f'%{search}%'
        args.extend([like, like])
    query += ' ORDER BY created_at DESC'
    rows = query_db(query, args)
    result = []
    for r in rows:
        r = dict(r)
        try:
            r['user_fields'] = json.loads(r['user_fields']) if r.get('user_fields') else {}
        except Exception:
            r['user_fields'] = {}
        result.append(r)
    return jsonify(result)


# ── Get single contact ──────────────────────────────────────────────────────
@bp.route('/api/wa/contacts/<path:phone>', methods=['GET'])
def get_wa_contact(phone):
    row = query_db('SELECT * FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    row = dict(row)
    try:
        row['user_fields'] = json.loads(row['user_fields']) if row.get('user_fields') else {}
    except Exception:
        row['user_fields'] = {}
    return jsonify(row)


# ── Register contact manually ───────────────────────────────────────────────
@bp.route('/api/wa/contacts', methods=['POST'])
def create_wa_contact():
    d = request.json or {}
    phone = (d.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'phone required'}), 400
    entity_type = d.get('entity_type', '')
    entity_id = d.get('entity_id')
    fields = _build_user_fields(entity_type, entity_id) if entity_type and entity_id else {}
    fields.update({k: v for k, v in d.items() if k not in ('phone', 'entity_type', 'entity_id')})
    name = fields.get('name', '') or d.get('name', '')
    existing = query_db('SELECT id FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    if existing:
        execute_db(
            'UPDATE wa_contacts SET name=?, entity_type=?, entity_id=?, user_fields=?, updated_at=CURRENT_TIMESTAMP WHERE phone=?',
            (name, entity_type, entity_id, json.dumps(fields, ensure_ascii=False), phone)
        )
        row = query_db('SELECT * FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    else:
        nid = insert_db(
            'INSERT INTO wa_contacts (phone, name, entity_type, entity_id, language, user_fields) VALUES (?, ?, ?, ?, ?, ?)',
            (phone, name, entity_type, entity_id, fields.get('language', 'ru'),
             json.dumps(fields, ensure_ascii=False))
        )
        row = query_db('SELECT * FROM wa_contacts WHERE id = ?', (nid,), one=True)
    row = dict(row)
    try:
        row['user_fields'] = json.loads(row['user_fields']) if row.get('user_fields') else {}
    except Exception:
        row['user_fields'] = {}
    return jsonify(row), 201


# ── Entity-specific registration shortcuts ──────────────────────────────────
def _register_from_entity(entity_type, entity_id):
    phone = _get_entity_phone(entity_type, entity_id)
    if not phone:
        return jsonify({'error': f'No phone for {entity_type} #{entity_id}'}), 400
    fields = _build_user_fields(entity_type, entity_id)
    name = fields.get('name', '')
    existing = query_db('SELECT id FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    if existing:
        execute_db(
            'UPDATE wa_contacts SET name=?, entity_type=?, entity_id=?, user_fields=? WHERE phone=?',
            (name, entity_type, entity_id, json.dumps(fields, ensure_ascii=False), phone)
        )
    else:
        insert_db(
            'INSERT INTO wa_contacts (phone, name, entity_type, entity_id, language, user_fields) VALUES (?, ?, ?, ?, ?, ?)',
            (phone, name, entity_type, entity_id, fields.get('language', 'ru'),
             json.dumps(fields, ensure_ascii=False))
        )
    row = query_db('SELECT * FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    row = dict(row)
    try:
        row['user_fields'] = json.loads(row['user_fields']) if row.get('user_fields') else {}
    except Exception:
        row['user_fields'] = {}
    return jsonify(row), 201


@bp.route('/api/wa/contacts/from-tenant/<int:eid>', methods=['POST'])
def register_tenant(eid):
    return _register_from_entity('tenant', eid)

@bp.route('/api/wa/contacts/from-professional/<int:eid>', methods=['POST'])
def register_professional(eid):
    return _register_from_entity('professional', eid)

@bp.route('/api/wa/contacts/from-owner/<int:eid>', methods=['POST'])
def register_owner(eid):
    return _register_from_entity('owner', eid)

@bp.route('/api/wa/contacts/from-team/<int:eid>', methods=['POST'])
def register_team(eid):
    return _register_from_entity('team', eid)


# ── Update contact ──────────────────────────────────────────────────────────
@bp.route('/api/wa/contacts/<path:phone>', methods=['PUT'])
def update_wa_contact(phone):
    row = query_db('SELECT * FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    d = request.json or {}
    fields = d.get('user_fields', {})
    execute_db(
        'UPDATE wa_contacts SET name=?, email=?, language=?, preferred_channel=?, opted_out=?, user_fields=? WHERE phone=?',
        (d.get('name', row['name']), d.get('email', row['email']),
         d.get('language', row['language']), d.get('preferred_channel', row['preferred_channel']),
         int(d.get('opted_out', row['opted_out'])),
         json.dumps(fields, ensure_ascii=False) if fields else row['user_fields'],
         phone)
    )
    updated = query_db('SELECT * FROM wa_contacts WHERE phone = ?', (phone,), one=True)
    updated = dict(updated)
    try:
        updated['user_fields'] = json.loads(updated['user_fields']) if updated.get('user_fields') else {}
    except Exception:
        updated['user_fields'] = {}
    return jsonify(updated)


# ── Delete contact ──────────────────────────────────────────────────────────
@bp.route('/api/wa/contacts/<path:phone>', methods=['DELETE'])
def delete_wa_contact(phone):
    execute_db('DELETE FROM wa_contacts WHERE phone = ?', (phone,))
    return jsonify({'ok': True})


# ── Available placeholder fields (for template builder) ─────────────────────
@bp.route('/api/wa/placeholder-fields', methods=['GET'])
def placeholder_fields():
    """Returns list of available {{placeholder}} names and descriptions."""
    return jsonify([
        {'key': 'name',       'label': 'Full Name',       'example': 'Inna Chuh'},
        {'key': 'phone',      'label': 'Phone',            'example': '+380634670272'},
        {'key': 'email',      'label': 'Email',            'example': 'tenant@email.com'},
        {'key': 'apartment',  'label': 'Apartment #',      'example': '134'},
        {'key': 'building',   'label': 'Building Name',    'example': 'Tower Chekalov'},
        {'key': 'rent',       'label': 'Rent Amount',      'example': '1500'},
        {'key': 'currency',   'label': 'Currency',         'example': 'USD'},
        {'key': 'lease_end',  'label': 'Lease End Date',   'example': '2026-07-05'},
        {'key': 'category',   'label': 'Pro Category',     'example': 'Plumbing'},
        {'key': 'role',       'label': 'Team Role',        'example': 'Manager'},
        {'key': 'language',   'label': 'Language',         'example': 'ru'},
    ])
