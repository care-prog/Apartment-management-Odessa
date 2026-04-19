"""
File upload + task patch endpoints.
"""
import os
import json
import uuid
from flask import Blueprint, request, jsonify, send_from_directory
from src.models import query_db, insert_db, execute_db

bp = Blueprint('uploads', __name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(ROOT, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)


@bp.route('/api/tasks/<int:tid>/status', methods=['PATCH'])
def patch_status(tid):
    data = request.json or {}
    new_status = data.get('status')
    if new_status not in ('pending', 'in_progress', 'done'):
        return jsonify({'error': 'invalid status'}), 400
    execute_db('UPDATE tasks SET status = ? WHERE id = ?', (new_status, tid))
    return jsonify({'ok': True, 'status': new_status})


@bp.route('/api/tasks/<int:tid>/detail', methods=['GET'])
def task_detail(tid):
    task = query_db('SELECT * FROM tasks WHERE id = ?', (tid,), one=True)
    if not task:
        return jsonify({'error': 'not found'}), 404
    files = query_db('SELECT * FROM documents WHERE doc_type = ? AND description = ?', ('task_attachment', f'task:{tid}'))
    task['attachments'] = files
    return jsonify(task)


@bp.route('/api/tasks/<int:tid>/attachments', methods=['POST'])
def upload_task_file(tid):
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400

    safe_name = f.filename.replace('/', '_').replace('\\', '_')
    unique = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(UPLOAD_DIR, unique)
    f.save(save_path)

    file_url = f'/uploads/{unique}'
    did = insert_db(
        'INSERT INTO documents (doc_type, file_url, description) VALUES (?, ?, ?)',
        ('task_attachment', file_url, f'task:{tid}')
    )
    return jsonify({'id': did, 'file_url': file_url, 'filename': safe_name}), 201


@bp.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)
