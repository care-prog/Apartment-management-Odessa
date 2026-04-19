from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('properties', __name__)

@bp.route('/api/properties', methods=['GET'])
def list_properties():
    rows = query_db('''
        SELECT p.*, o.name as owner_name,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id) as total_units,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id AND status = 'occupied') as occupied_units
        FROM properties p
        LEFT JOIN owners o ON p.owner_id = o.id
        ORDER BY p.name
    ''')
    return jsonify(rows)

@bp.route('/api/properties', methods=['POST'])
def create_property():
    data = request.json
    pid = insert_db(
        'INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)',
        (data['name'], data.get('address'), data.get('type', 'residential'),
         data.get('status', 'active'), data.get('owner_id'), data.get('notes'))
    )
    return jsonify({'id': pid}), 201

@bp.route('/api/properties/<int:pid>', methods=['GET'])
def get_property(pid):
    row = query_db('SELECT p.*, o.name as owner_name FROM properties p LEFT JOIN owners o ON p.owner_id = o.id WHERE p.id = ?', (pid,), one=True)
    if not row:
        return jsonify({'error': 'Not found'}), 404
    row['apartments'] = query_db('SELECT * FROM apartments WHERE property_id = ? ORDER BY number', (pid,))
    return jsonify(row)

@bp.route('/api/properties/<int:pid>', methods=['PUT'])
def update_property(pid):
    data = request.json
    execute_db(
        'UPDATE properties SET name=?, address=?, type=?, status=?, owner_id=?, notes=? WHERE id=?',
        (data['name'], data.get('address'), data.get('type'), data.get('status'),
         data.get('owner_id'), data.get('notes'), pid)
    )
    return jsonify({'ok': True})

@bp.route('/api/apartments', methods=['GET'])
def list_apartments():
    property_id = request.args.get('property_id')
    if property_id:
        rows = query_db('SELECT a.*, p.name as property_name FROM apartments a JOIN properties p ON a.property_id = p.id WHERE a.property_id = ? ORDER BY a.number', (property_id,))
    else:
        rows = query_db('SELECT a.*, p.name as property_name FROM apartments a JOIN properties p ON a.property_id = p.id ORDER BY p.name, a.number')
    return jsonify(rows)

@bp.route('/api/apartments', methods=['POST'])
def create_apartment():
    data = request.json
    aid = insert_db(
        'INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (data['property_id'], data['number'], data.get('floor'), data.get('rooms'),
         data.get('status', 'vacant'), data.get('monthly_rent', 0), data.get('currency', 'USD'), data.get('notes'))
    )
    return jsonify({'id': aid}), 201

@bp.route('/api/apartments/<int:aid>', methods=['PUT'])
def update_apartment(aid):
    data = request.json
    execute_db(
        'UPDATE apartments SET number=?, floor=?, rooms=?, status=?, monthly_rent=?, currency=?, notes=? WHERE id=?',
        (data['number'], data.get('floor'), data.get('rooms'), data.get('status'),
         data.get('monthly_rent'), data.get('currency', 'USD'), data.get('notes'), aid)
    )
    return jsonify({'ok': True})

@bp.route('/api/properties/<int:pid>', methods=['DELETE'])
def delete_property(pid):
    # FK-safe: delete apartments (and their dependents) first
    apts = query_db('SELECT id FROM apartments WHERE property_id = ?', (pid,))
    for a in apts:
        aid = a['id']
        execute_db('DELETE FROM payments WHERE lease_id IN (SELECT id FROM leases WHERE apartment_id = ?)', (aid,))
        execute_db('DELETE FROM leases WHERE apartment_id = ?', (aid,))
        execute_db('DELETE FROM maintenance_orders WHERE apartment_id = ?', (aid,))
        execute_db('DELETE FROM warranties WHERE apartment_id = ?', (aid,))
        execute_db('DELETE FROM meter_readings WHERE apartment_id = ?', (aid,))
        execute_db('DELETE FROM utility_bills WHERE apartment_id = ?', (aid,))
        execute_db('DELETE FROM documents WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM apartments WHERE property_id = ?', (pid,))
    execute_db('DELETE FROM documents WHERE property_id = ?', (pid,))
    execute_db('DELETE FROM properties WHERE id = ?', (pid,))
    return jsonify({'ok': True})

@bp.route('/api/apartments/<int:aid>', methods=['DELETE'])
def delete_apartment(aid):
    execute_db('DELETE FROM payments WHERE lease_id IN (SELECT id FROM leases WHERE apartment_id = ?)', (aid,))
    execute_db('DELETE FROM leases WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM maintenance_orders WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM warranties WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM meter_readings WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM utility_bills WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM documents WHERE apartment_id = ?', (aid,))
    execute_db('DELETE FROM apartments WHERE id = ?', (aid,))
    return jsonify({'ok': True})

@bp.route('/api/owners', methods=['GET'])
def list_owners():
    return jsonify(query_db('SELECT * FROM owners ORDER BY name'))

@bp.route('/api/owners', methods=['POST'])
def create_owner():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    # Accept both 'contact' (legacy) and 'phone' field
    phone = data.get('phone') or data.get('contact') or ''
    oid = insert_db(
        'INSERT INTO owners (name, contact, phone, email, bank_details, report_schedule, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (name, phone, phone,
         data.get('email', ''), data.get('bank_details', ''),
         data.get('report_schedule'), data.get('notes', ''))
    )
    return jsonify({'id': oid}), 201

@bp.route('/api/owners/<int:oid>', methods=['PUT'])
def update_owner(oid):
    data = request.json
    execute_db(
        'UPDATE owners SET name=?, phone=?, email=?, bank_details=?, notes=? WHERE id=?',
        (data.get('name'), data.get('phone'), data.get('email'),
         data.get('bank_details'), data.get('notes'), oid)
    )
    return jsonify({'ok': True})


@bp.route('/api/owners/<int:oid>/detail', methods=['GET'])
def owner_detail(oid):
    owner = query_db('SELECT * FROM owners WHERE id = ?', (oid,), one=True)
    if not owner:
        return jsonify({'error': 'Not found'}), 404

    properties = query_db('''
        SELECT p.*,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id) as total_units,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id AND status = 'occupied') as occupied_units,
            (SELECT COALESCE(SUM(l.rent_amount), 0) FROM leases l
             JOIN apartments a ON l.apartment_id = a.id
             WHERE a.property_id = p.id AND l.status = 'active') as monthly_rent
        FROM properties p WHERE p.owner_id = ?
    ''', (oid,))

    payments = query_db(
        'SELECT * FROM owner_payments WHERE owner_id = ? ORDER BY payment_date DESC',
        (oid,)
    )
    total_paid = sum(p['amount'] for p in payments)

    total_rent = sum(p['monthly_rent'] for p in properties)
    fee_pct = 0.10
    owner_monthly = round(total_rent * (1 - fee_pct), 2)

    documents = query_db('''
        SELECT d.* FROM documents d
        JOIN properties p ON d.property_id = p.id
        WHERE p.owner_id = ?
        ORDER BY d.uploaded_at DESC
    ''', (oid,))

    return jsonify({
        'owner': owner,
        'properties': properties,
        'payments': payments,
        'documents': documents,
        'financials': {
            'total_monthly_rent': total_rent,
            'management_fee': round(total_rent * fee_pct, 2),
            'owner_monthly': owner_monthly,
            'total_paid': total_paid,
            'balance_owed': round(owner_monthly - total_paid, 2),
        }
    })


@bp.route('/api/properties/<int:pid>/documents', methods=['GET'])
def property_documents(pid):
    docs = query_db(
        'SELECT * FROM documents WHERE property_id = ? ORDER BY uploaded_at DESC',
        (pid,)
    )
    return jsonify(docs)


@bp.route('/api/properties/<int:pid>/documents', methods=['POST'])
def upload_property_document(pid):
    import os, uuid
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    from src.routes.uploads import UPLOAD_DIR
    safe_name = f.filename.replace('/', '_').replace('\\', '_')
    unique = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(UPLOAD_DIR, unique)
    f.save(save_path)
    file_url = f'/uploads/{unique}'
    doc_type = request.form.get('doc_type', 'document')
    description = request.form.get('description', '')
    did = insert_db(
        'INSERT INTO documents (property_id, doc_type, file_url, description) VALUES (?, ?, ?, ?)',
        (pid, doc_type, file_url, description)
    )
    return jsonify({'id': did, 'file_url': file_url, 'filename': safe_name}), 201


@bp.route('/api/properties/<int:pid>/detail', methods=['GET'])
def property_detail_page(pid):
    prop = query_db('''
        SELECT p.*, o.name as owner_name, o.id as owner_id
        FROM properties p LEFT JOIN owners o ON p.owner_id = o.id
        WHERE p.id = ?
    ''', (pid,), one=True)
    if not prop:
        return jsonify({'error': 'Not found'}), 404

    apartments = query_db('SELECT * FROM apartments WHERE property_id = ? ORDER BY number', (pid,))

    leases = query_db('''
        SELECT l.*, t.name as tenant_name, a.number as apt_number
        FROM leases l JOIN tenants t ON l.tenant_id = t.id JOIN apartments a ON l.apartment_id = a.id
        WHERE a.property_id = ? AND l.status = 'active' ORDER BY a.number
    ''', (pid,))

    owner_payments = []
    if prop.get('owner_id'):
        owner_payments = query_db(
            'SELECT * FROM owner_payments WHERE owner_id = ? ORDER BY payment_date DESC',
            (prop['owner_id'],)
        )

    documents = query_db(
        'SELECT * FROM documents WHERE property_id = ? ORDER BY uploaded_at DESC',
        (pid,)
    )

    total_rent = sum(l['rent_amount'] for l in leases)
    fee_pct = 0.10
    management_fee = round(total_rent * fee_pct, 2)
    owner_receives = round(total_rent - management_fee, 2)
    total_paid = sum(op['amount'] for op in owner_payments)

    return jsonify({
        'property': prop,
        'apartments': apartments,
        'leases': leases,
        'owner_payments': owner_payments,
        'documents': documents,
        'financials': {
            'monthly_rent': total_rent,
            'management_fee': management_fee,
            'owner_receives': owner_receives,
            'total_paid_to_owner': total_paid,
            'balance_owed': round(owner_receives - total_paid, 2),
        }
    })


@bp.route('/api/owners/<int:oid>', methods=['DELETE'])
def delete_owner(oid):
    execute_db('DELETE FROM owners WHERE id = ?', (oid,))
    return jsonify({'ok': True})


@bp.route('/api/properties/unassigned', methods=['GET'])
def unassigned_properties():
    """Return properties with no owner assigned."""
    rows = query_db('''
        SELECT p.id, p.name, p.address,
               COUNT(a.id) as total_units
        FROM properties p
        LEFT JOIN apartments a ON a.property_id = p.id
        WHERE p.owner_id IS NULL OR p.owner_id = 0
        GROUP BY p.id ORDER BY p.name
    ''')
    return jsonify(rows)

@bp.route('/api/owners/<int:oid>/assign-property', methods=['POST'])
def assign_property_to_owner(oid):
    """Assign a property to this owner."""
    data = request.json or {}
    pid = data.get('property_id')
    if not pid:
        return jsonify({'error': 'property_id required'}), 400
    execute_db('UPDATE properties SET owner_id = ? WHERE id = ?', (oid, pid))
    return jsonify({'ok': True})

@bp.route('/api/owners/<int:oid>/remove-property/<int:pid>', methods=['DELETE'])
def remove_property_from_owner(oid, pid):
    """Remove owner assignment from a property."""
    execute_db('UPDATE properties SET owner_id = NULL WHERE id = ? AND owner_id = ?', (pid, oid))
    return jsonify({'ok': True})

@bp.route('/api/leases/<int:lid>/collect', methods=['POST'])
def collect_rent(lid):
    """Mark rent as collected for this month and log payment."""
    from datetime import date as _dt
    data = request.json or {}
    lease = query_db('SELECT * FROM leases WHERE id = ?', (lid,), one=True)
    if not lease:
        return jsonify({'error': 'Lease not found'}), 404
    payment_date = data.get('payment_date') or _dt.today().isoformat()
    amount = data.get('amount') or lease['rent_amount']
    pid = insert_db(
        'INSERT INTO payments (lease_id, type, amount, payment_date, method, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (lid, 'rent', amount, payment_date, data.get('method', 'cash'), 'paid', data.get('notes', ''))
    )
    from src.routes.activity import log_action
    log_action('create', 'payment', pid, f'Rent collected: lease #{lid}, ${amount} on {payment_date}')
    return jsonify({'ok': True, 'payment_id': pid})
