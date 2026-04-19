from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('tasks', __name__)

@bp.route('/api/tasks', methods=['GET'])
def list_tasks():
    status = request.args.get('status')
    assigned = request.args.get('assigned_to')
    query = 'SELECT * FROM tasks WHERE 1=1'
    args = []
    if status:
        query += ' AND status = ?'
        args.append(status)
    if assigned:
        query += ' AND assigned_to = ?'
        args.append(assigned)
    query += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 END, due_date"
    return jsonify(query_db(query, args))

@bp.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.json
    tid = insert_db(
        'INSERT INTO tasks (title, description, assigned_to, due_date, status, priority, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['title'], data.get('description'), data.get('assigned_to'),
         data.get('due_date'), data.get('status', 'pending'),
         data.get('priority', 'normal'), data.get('notes'))
    )
    return jsonify({'id': tid}), 201

@bp.route('/api/tasks/<int:tid>', methods=['PUT'])
def update_task(tid):
    data = request.json
    execute_db(
        'UPDATE tasks SET title=?, description=?, assigned_to=?, due_date=?, status=?, priority=?, notes=? WHERE id=?',
        (data.get('title'), data.get('description'), data.get('assigned_to'),
         data.get('due_date'), data.get('status'), data.get('priority'), data.get('notes'), tid)
    )
    return jsonify({'ok': True})

@bp.route('/api/tasks/<int:tid>', methods=['DELETE'])
def delete_task(tid):
    execute_db('DELETE FROM tasks WHERE id = ?', (tid,))
    return jsonify({'ok': True})
