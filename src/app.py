import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify, request
from src.models import init_db
from src.routes import properties, tenants, payments, utilities, maintenance, tasks, dashboard, finance, whatsapp, chat, uploads, wallets, activity, users
from src.monday_sync import sync_to_db, fetch_board_items, parse_item
from src.auth import init_auth

app = Flask(__name__, static_folder=None)

# CORS for /api/whatsapp-query (called from browser console on WhatsApp Web)
@app.after_request
def add_cors(response):
    if request.path == '/api/whatsapp-query':
        response.headers['Access-Control-Allow-Origin'] = 'https://web.whatsapp.com'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/api/whatsapp-query', methods=['OPTIONS'])
def whatsapp_options():
    return '', 204

@app.route('/whatsapp-bot.js')
def serve_bot_script():
    bot_path = os.path.join(ROOT, 'whatsapp-bot', 'browser-script.js')
    with open(bot_path) as f:
        body = f.read()
    return body, 200, {
        'Content-Type': 'application/javascript',
        'Access-Control-Allow-Origin': '*',
    }

init_auth(app)

app.register_blueprint(properties.bp)
app.register_blueprint(tenants.bp)
app.register_blueprint(payments.bp)
app.register_blueprint(utilities.bp)
app.register_blueprint(maintenance.bp)
app.register_blueprint(tasks.bp)
app.register_blueprint(dashboard.bp)
app.register_blueprint(finance.bp)
app.register_blueprint(whatsapp.bp)
app.register_blueprint(chat.bp)
app.register_blueprint(uploads.bp)
app.register_blueprint(wallets.bp)
app.register_blueprint(activity.bp)
app.register_blueprint(users.bp)

ROOT = os.path.dirname(os.path.dirname(__file__))

@app.route('/api/sync', methods=['POST'])
def sync_monday():
    try:
        result = sync_to_db()
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'synced': 0, 'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/sync/push', methods=['POST'])
def sync_push():
    """Accepts raw Monday items from Make.com and syncs to DB. Requires X-Sync-Secret header."""
    from src.auth import _get_app_password
    secret = _get_app_password()
    if secret and request.headers.get('X-Sync-Secret') != secret:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    if not data or 'items' not in data:
        return jsonify({'error': 'Expected {items: [...]}'}), 400
    try:
        result = sync_to_db(items=data['items'])
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'synced': 0, 'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/api/me', methods=['GET'])
def current_user():
    from src.auth import get_current_user
    user = get_current_user()
    if not user:
        return jsonify({'role': 'guest', 'is_owner': False, 'display_name': 'Guest', 'permissions': '{}', 'property_ids': '[]'})
    return jsonify({
        'id': user.get('id'),
        'role': user.get('role', 'guest'),
        'is_owner': user.get('role') == 'owner',
        'display_name': user.get('display_name', 'User'),
        'permissions': user.get('permissions', '{}'),
        'property_ids': user.get('property_ids', '[]'),
    })

@app.route('/api/sync/test', methods=['GET'])
def sync_test():
    """Diagnostic endpoint — shows Monday API connection status."""
    from src.monday_sync import get_token, get_board_id, monday_query
    token = get_token()
    board_id = get_board_id()
    if not token:
        return jsonify({'ok': False, 'error': 'MONDAY_API_TOKEN not set'})
    result = monday_query('{ me { name } }')
    return jsonify({'ok': 'error' not in result, 'board_id': board_id, 'monday': result})

@app.route('/api/monday/raw', methods=['GET'])
def monday_raw():
    items = fetch_board_items()
    return jsonify([parse_item(i) for i in items])

@app.route('/')
def index():
    return send_from_directory(ROOT, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(ROOT, path)

# Auto-init DB on import (needed for gunicorn/Render)
init_db()
from src.models import safe_migrate
safe_migrate()
from src.models import query_db
if not query_db('SELECT COUNT(*) as c FROM properties', one=True)['c']:
    seed_path = os.path.join(ROOT, 'database', 'seeds', 'seed_data.py')
    if os.path.exists(seed_path):
        exec(open(seed_path).read())
        print("Database seeded with initial data.")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Starting server at http://localhost:{port}")
    app.run(debug=True, port=port)
