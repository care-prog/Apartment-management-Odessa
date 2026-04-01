from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('utilities', __name__)

@bp.route('/api/meter-readings', methods=['GET'])
def list_readings():
    apartment_id = request.args.get('apartment_id')
    query = '''
        SELECT mr.*, a.number as apt_number, p.name as property_name
        FROM meter_readings mr
        JOIN apartments a ON mr.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE 1=1
    '''
    args = []
    if apartment_id:
        query += ' AND mr.apartment_id = ?'
        args.append(apartment_id)
    query += ' ORDER BY mr.reading_date DESC'
    return jsonify(query_db(query, args))

@bp.route('/api/meter-readings', methods=['POST'])
def create_reading():
    data = request.json
    mid = insert_db(
        'INSERT INTO meter_readings (apartment_id, meter_type, reading_value, reading_date, photo_url, submitted_to, submitted, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (data['apartment_id'], data['meter_type'], data['reading_value'],
         data['reading_date'], data.get('photo_url'), data.get('submitted_to'),
         data.get('submitted', 0), data.get('notes'))
    )
    return jsonify({'id': mid}), 201

@bp.route('/api/meter-readings/<int:mid>', methods=['PUT'])
def update_reading(mid):
    data = request.json
    execute_db('UPDATE meter_readings SET submitted=?, submitted_to=?, notes=? WHERE id=?',
               (data.get('submitted', 0), data.get('submitted_to'), data.get('notes'), mid))
    return jsonify({'ok': True})

@bp.route('/api/utility-bills', methods=['GET'])
def list_bills():
    apartment_id = request.args.get('apartment_id')
    status = request.args.get('status')
    query = '''
        SELECT ub.*, a.number as apt_number, p.name as property_name
        FROM utility_bills ub
        JOIN apartments a ON ub.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE 1=1
    '''
    args = []
    if apartment_id:
        query += ' AND ub.apartment_id = ?'
        args.append(apartment_id)
    if status:
        query += ' AND ub.status = ?'
        args.append(status)
    query += ' ORDER BY ub.due_date DESC'
    return jsonify(query_db(query, args))

@bp.route('/api/utility-bills', methods=['POST'])
def create_bill():
    data = request.json
    bid = insert_db(
        'INSERT INTO utility_bills (apartment_id, period, bill_type, amount, status, due_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['apartment_id'], data['period'], data['bill_type'], data['amount'],
         data.get('status', 'pending'), data.get('due_date'), data.get('notes'))
    )
    return jsonify({'id': bid}), 201
