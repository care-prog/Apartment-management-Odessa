from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db
from src.routes.activity import log_action

bp = Blueprint('maintenance', __name__)

@bp.route('/api/maintenance', methods=['GET'])
def list_orders():
    status = request.args.get('status')
    query = '''
        SELECT mo.*, a.number as apt_number, p.name as property_name,
               w.appliance as warranty_appliance, w.end_date as warranty_end
        FROM maintenance_orders mo
        JOIN apartments a ON mo.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        LEFT JOIN warranties w ON mo.warranty_id = w.id
        WHERE 1=1
    '''
    args = []
    if status:
        query += ' AND mo.status = ?'
        args.append(status)
    query += ' ORDER BY mo.created_at DESC'
    return jsonify(query_db(query, args))

@bp.route('/api/maintenance', methods=['POST'])
def create_order():
    data = request.json
    oid = insert_db(
        'INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to, cost, warranty_id) VALUES (?, ?, ?, ?, ?, ?)',
        (data['apartment_id'], data['description'], data.get('status', 'reported'),
         data.get('assigned_to'), data.get('cost'), data.get('warranty_id'))
    )
    log_action('create', 'maintenance', oid,
               f"New maintenance order: {data['description'][:60]} (apt {data['apartment_id']})")
    return jsonify({'id': oid}), 201

@bp.route('/api/maintenance/<int:oid>', methods=['PUT'])
def update_order(oid):
    data = request.json
    before = query_db('SELECT * FROM maintenance_orders WHERE id = ?', (oid,), one=True)
    execute_db(
        'UPDATE maintenance_orders SET status=?, assigned_to=?, cost=?, completed_at=? WHERE id=?',
        (data.get('status'), data.get('assigned_to'), data.get('cost'), data.get('completed_at'), oid)
    )
    log_action('update', 'maintenance', oid,
               f"Maintenance order #{oid} → {data.get('status', 'updated')}",
               before_data=dict(before) if before else None)
    return jsonify({'ok': True})

@bp.route('/api/warranties', methods=['GET'])
def list_warranties():
    return jsonify(query_db('''
        SELECT w.*, a.number as apt_number, p.name as property_name
        FROM warranties w
        JOIN apartments a ON w.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        ORDER BY w.end_date
    '''))

@bp.route('/api/warranties', methods=['POST'])
def create_warranty():
    data = request.json
    wid = insert_db(
        'INSERT INTO warranties (apartment_id, appliance, start_date, end_date, provider, document_url, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['apartment_id'], data['appliance'], data.get('start_date'),
         data.get('end_date'), data.get('provider'), data.get('document_url'), data.get('notes'))
    )
    log_action('create', 'warranty', wid,
               f"New warranty: {data['appliance']} (apt {data['apartment_id']}, expires {data.get('end_date','?')})")
    return jsonify({'id': wid}), 201
