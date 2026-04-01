from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db

bp = Blueprint('payments', __name__)

@bp.route('/api/payments', methods=['GET'])
def list_payments():
    lease_id = request.args.get('lease_id')
    status = request.args.get('status')
    query = '''
        SELECT pay.*, t.name as tenant_name, a.number as apt_number, p.name as property_name
        FROM payments pay
        JOIN leases l ON pay.lease_id = l.id
        JOIN tenants t ON l.tenant_id = t.id
        JOIN apartments a ON l.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE 1=1
    '''
    args = []
    if lease_id:
        query += ' AND pay.lease_id = ?'
        args.append(lease_id)
    if status:
        query += ' AND pay.status = ?'
        args.append(status)
    query += ' ORDER BY pay.payment_date DESC'
    return jsonify(query_db(query, args))

@bp.route('/api/payments', methods=['POST'])
def create_payment():
    data = request.json
    pid = insert_db(
        'INSERT INTO payments (lease_id, type, amount, payment_date, method, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['lease_id'], data.get('type', 'rent'), data['amount'],
         data.get('payment_date'), data.get('method', 'cash'),
         data.get('status', 'paid'), data.get('notes'))
    )
    return jsonify({'id': pid}), 201

@bp.route('/api/payments/<int:pid>', methods=['PUT'])
def update_payment(pid):
    data = request.json
    from src.models import execute_db
    execute_db(
        'UPDATE payments SET status=?, payment_date=?, notes=? WHERE id=?',
        (data.get('status'), data.get('payment_date'), data.get('notes'), pid)
    )
    return jsonify({'ok': True})
