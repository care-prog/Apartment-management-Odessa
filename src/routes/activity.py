"""Activity log — records all write operations and supports undo/restore."""
import json
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('activity', __name__)


def log_action(action, entity_type, entity_id=None, description=None, before_data=None, user_role='owner'):
    """Call this from any route to record an action."""
    try:
        insert_db(
            'INSERT INTO activity_log (action, entity_type, entity_id, description, before_data, user_role, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (action, entity_type, str(entity_id) if entity_id else None,
             description,
             json.dumps(before_data, ensure_ascii=False) if before_data else None,
             user_role,
             request.remote_addr if request else None)
        )
    except Exception:
        pass  # Never let logging break the main action


@bp.route('/api/activity', methods=['GET'])
def list_activity():
    limit = int(request.args.get('limit', 200))
    entity = request.args.get('entity_type')
    action = request.args.get('action')
    query = 'SELECT * FROM activity_log WHERE 1=1'
    args = []
    if entity:
        query += ' AND entity_type = ?'
        args.append(entity)
    if action:
        query += ' AND action = ?'
        args.append(action)
    query += ' ORDER BY created_at DESC LIMIT ?'
    args.append(limit)
    rows = query_db(query, args)
    # Parse before_data JSON for frontend
    for r in rows:
        if r.get('before_data'):
            try:
                r['before_data'] = json.loads(r['before_data'])
            except Exception:
                pass
    return jsonify(rows)


@bp.route('/api/activity/<int:lid>/restore', methods=['POST'])
def restore_action(lid):
    """Attempt to restore a deleted entity from the before_data snapshot."""
    entry = query_db('SELECT * FROM activity_log WHERE id = ?', (lid,), one=True)
    if not entry:
        return jsonify({'error': 'Log entry not found'}), 404
    if entry['action'] != 'delete':
        return jsonify({'error': 'Only delete actions can be restored'}), 400
    raw = entry.get('before_data')
    if not raw:
        return jsonify({'error': 'No snapshot data available for restore'}), 400

    data = json.loads(raw) if isinstance(raw, str) else raw
    entity = entry['entity_type']

    try:
        if entity == 'task':
            new_id = insert_db(
                'INSERT INTO tasks (title, description, assigned_to, due_date, status, priority, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (data.get('title'), data.get('description'), data.get('assigned_to'),
                 data.get('due_date'), data.get('status', 'pending'),
                 data.get('priority', 'normal'), data.get('notes'))
            )
            log_action('restore', 'task', new_id, f"Restored task: {data.get('title')}")
            return jsonify({'ok': True, 'new_id': new_id})

        elif entity == 'tenant':
            new_id = insert_db(
                'INSERT INTO tenants (name, phone, email, language, notes) VALUES (?, ?, ?, ?, ?)',
                (data.get('name'), data.get('phone'), data.get('email'),
                 data.get('language', 'ru'), data.get('notes'))
            )
            log_action('restore', 'tenant', new_id, f"Restored tenant: {data.get('name')}")
            return jsonify({'ok': True, 'new_id': new_id})

        elif entity == 'expense':
            new_id = insert_db(
                'INSERT INTO office_expenses (description, amount, category, date, currency) VALUES (?, ?, ?, ?, ?)',
                (data.get('description'), data.get('amount'), data.get('category'),
                 data.get('date'), data.get('currency', 'USD'))
            )
            log_action('restore', 'expense', new_id, f"Restored expense: {data.get('description')}")
            return jsonify({'ok': True, 'new_id': new_id})

        elif entity == 'transaction':
            new_id = insert_db(
                'INSERT INTO cash_transactions (type, amount, currency, category, description, transaction_date) VALUES (?, ?, ?, ?, ?, ?)',
                (data.get('type'), data.get('amount'), data.get('currency', 'USD'),
                 data.get('category'), data.get('description'), data.get('transaction_date'))
            )
            log_action('restore', 'transaction', new_id, f"Restored transaction: {data.get('description')}")
            return jsonify({'ok': True, 'new_id': new_id})

        else:
            return jsonify({'error': f'Restore not supported for entity type: {entity}'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500
