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

@bp.route('/api/owners', methods=['GET'])
def list_owners():
    return jsonify(query_db('SELECT * FROM owners ORDER BY name'))

@bp.route('/api/owners', methods=['POST'])
def create_owner():
    data = request.json
    oid = insert_db(
        'INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)',
        (data['name'], data.get('contact'), data.get('report_schedule'), data.get('notes'))
    )
    return jsonify({'id': oid}), 201
