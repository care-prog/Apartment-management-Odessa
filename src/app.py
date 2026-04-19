import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify, request
from src.models import init_db
from src.routes import properties, tenants, payments, utilities, maintenance, tasks, dashboard, finance, whatsapp, chat, uploads
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

ROOT = os.path.dirname(os.path.dirname(__file__))

@app.route('/api/sync', methods=['POST'])
def sync_monday():
    try:
        result = sync_to_db()
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'synced': 0, 'error': str(e), 'trace': traceback.format_exc()}), 500

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
