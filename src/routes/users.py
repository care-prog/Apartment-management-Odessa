"""User management — app_users CRUD (owner-only access)."""
import hashlib
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('users', __name__)


def _hash_password(password):
    return hashlib.sha256(('apt-mgmt-user-' + password).encode()).hexdigest()


@bp.route('/api/users', methods=['GET'])
def list_users():
    users = query_db('SELECT id, username, display_name, role, permissions, property_ids, is_active, created_at FROM app_users ORDER BY role, display_name')
    return jsonify(users)


@bp.route('/api/users', methods=['POST'])
def create_user():
    data = request.json
    password = data.get('password', '')
    if not password:
        return jsonify({'error': 'Password required'}), 400
    if not data.get('username'):
        return jsonify({'error': 'Username required'}), 400
    uid = insert_db(
        'INSERT INTO app_users (username, display_name, password_hash, role, permissions, property_ids, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)',
        (data['username'].strip().lower(),
         data.get('display_name', data['username']),
         _hash_password(password),
         data.get('role', 'office'),
         data.get('permissions', '{}'),
         data.get('property_ids', '[]'))
    )
    return jsonify({'id': uid}), 201


@bp.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    data = request.json
    # If password provided, update it
    if data.get('password'):
        execute_db(
            'UPDATE app_users SET display_name=?, role=?, permissions=?, property_ids=?, is_active=?, password_hash=? WHERE id=?',
            (data.get('display_name'), data.get('role'), data.get('permissions', '{}'),
             data.get('property_ids', '[]'), data.get('is_active', 1),
             _hash_password(data['password']), uid)
        )
    else:
        execute_db(
            'UPDATE app_users SET display_name=?, role=?, permissions=?, property_ids=?, is_active=? WHERE id=?',
            (data.get('display_name'), data.get('role'), data.get('permissions', '{}'),
             data.get('property_ids', '[]'), data.get('is_active', 1), uid)
        )
    return jsonify({'ok': True})


@bp.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    execute_db('DELETE FROM app_users WHERE id = ?', (uid,))
    return jsonify({'ok': True})
