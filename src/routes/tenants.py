from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('tenants', __name__)

@bp.route('/api/tenants', methods=['GET'])
def list_tenants():
    rows = query_db('''
        SELECT t.*, l.apartment_id, a.number as apt_number, p.name as property_name,
               l.rent_amount, l.start_date, l.end_date, l.status as lease_status
        FROM tenants t
        LEFT JOIN leases l ON t.id = l.tenant_id AND l.status = 'active'
        LEFT JOIN apartments a ON l.apartment_id = a.id
        LEFT JOIN properties p ON a.property_id = p.id
        ORDER BY t.name
    ''')
    return jsonify(rows)

@bp.route('/api/tenants', methods=['POST'])
def create_tenant():
    data = request.json
    tid = insert_db(
        'INSERT INTO tenants (name, phone, email, passport_info, language, notes) VALUES (?, ?, ?, ?, ?, ?)',
        (data['name'], data.get('phone'), data.get('email'),
         data.get('passport_info'), data.get('language', 'ru'), data.get('notes'))
    )
    return jsonify({'id': tid}), 201

@bp.route('/api/tenants/<int:tid>', methods=['PUT'])
def update_tenant(tid):
    data = request.json
    execute_db(
        'UPDATE tenants SET name=?, phone=?, email=?, passport_info=?, language=?, notes=? WHERE id=?',
        (data['name'], data.get('phone'), data.get('email'),
         data.get('passport_info'), data.get('language'), data.get('notes'), tid)
    )
    return jsonify({'ok': True})

@bp.route('/api/leases', methods=['GET'])
def list_leases():
    rows = query_db('''
        SELECT l.*, t.name as tenant_name, a.number as apt_number, p.name as property_name
        FROM leases l
        JOIN tenants t ON l.tenant_id = t.id
        JOIN apartments a ON l.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        ORDER BY l.end_date
    ''')
    return jsonify(rows)

@bp.route('/api/leases', methods=['POST'])
def create_lease():
    data = request.json
    lid = insert_db(
        'INSERT INTO leases (apartment_id, tenant_id, start_date, end_date, rent_amount, deposit, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (data['apartment_id'], data['tenant_id'], data['start_date'], data.get('end_date'),
         data['rent_amount'], data.get('deposit', 0), data.get('status', 'active'), data.get('notes'))
    )
    execute_db('UPDATE apartments SET status = ? WHERE id = ?', ('occupied', data['apartment_id']))
    return jsonify({'id': lid}), 201

@bp.route('/api/leases/<int:lid>', methods=['PUT'])
def update_lease(lid):
    data = request.json
    execute_db(
        'UPDATE leases SET start_date=?, end_date=?, rent_amount=?, deposit=?, status=?, notes=? WHERE id=?',
        (data.get('start_date'), data.get('end_date'), data.get('rent_amount'),
         data.get('deposit'), data.get('status'), data.get('notes'), lid)
    )
    return jsonify({'ok': True})

@bp.route('/api/tenants/<int:tid>', methods=['DELETE'])
def delete_tenant(tid):
    execute_db('DELETE FROM payments WHERE lease_id IN (SELECT id FROM leases WHERE tenant_id = ?)', (tid,))
    execute_db('DELETE FROM leases WHERE tenant_id = ?', (tid,))
    execute_db('DELETE FROM tenants WHERE id = ?', (tid,))
    return jsonify({'ok': True})

@bp.route('/api/leases/<int:lid>', methods=['DELETE'])
def delete_lease(lid):
    execute_db('DELETE FROM payments WHERE lease_id = ?', (lid,))
    execute_db('DELETE FROM leases WHERE id = ?', (lid,))
    return jsonify({'ok': True})
