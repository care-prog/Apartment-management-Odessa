import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify
from src.models import init_db
from src.routes import properties, tenants, payments, utilities, maintenance, tasks, dashboard
from src.monday_sync import sync_to_db, fetch_board_items, parse_item

app = Flask(__name__, static_folder=None)

app.register_blueprint(properties.bp)
app.register_blueprint(tenants.bp)
app.register_blueprint(payments.bp)
app.register_blueprint(utilities.bp)
app.register_blueprint(maintenance.bp)
app.register_blueprint(tasks.bp)
app.register_blueprint(dashboard.bp)

ROOT = os.path.dirname(os.path.dirname(__file__))

@app.route('/api/sync', methods=['POST'])
def sync_monday():
    result = sync_to_db()
    return jsonify(result)

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

if __name__ == '__main__':
    init_db()
    # Seed if DB is empty
    from src.models import query_db
    if not query_db('SELECT COUNT(*) as c FROM properties', one=True)['c']:
        seed_path = os.path.join(ROOT, 'database', 'seeds', 'seed_data.py')
        if os.path.exists(seed_path):
            exec(open(seed_path).read())
            print("Database seeded with initial data.")
    print("Starting server at http://localhost:5000")
    app.run(debug=True, port=5050)
