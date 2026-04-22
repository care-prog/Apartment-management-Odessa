import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify, request
from src.models import init_db
from src.routes import properties, tenants, payments, utilities, maintenance, tasks, dashboard, finance, whatsapp, chat, uploads, wallets, activity, users, professionals as professionals_mod
from src.routes import wa_contacts, wa_templates
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
app.register_blueprint(professionals_mod.bp)
app.register_blueprint(wa_contacts.bp)
app.register_blueprint(wa_templates.bp)

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

@app.route('/api/health', methods=['GET'])
def health_check():
    """Lightweight keepalive endpoint — no auth required."""
    return jsonify({'ok': True, 'status': 'running'}), 200

@app.route('/api/version', methods=['GET'])
def app_version():
    """Public version endpoint — helps verify which commit is deployed."""
    return jsonify({'version': 'df02bf0', 'features': ['owner-finance-reports', 'wa-token-ui', 'resilient-startup']}), 200

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

_db_initialized = False

@app.before_request
def _lazy_init_db():
    """Init DB on the very first request. Keeps gunicorn startup instant."""
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True
    try:
        init_db()
        print('[db] init_db OK')
    except Exception as _e:
        print(f'[db] init_db ERROR: {_e!r}')
    try:
        from src.models import safe_migrate
        safe_migrate()
        print('[db] safe_migrate OK')
    except Exception as _e:
        print(f'[db] safe_migrate ERROR: {_e!r}')
    try:
        from src.models import query_db as _qdb
        if not _qdb('SELECT COUNT(*) as c FROM properties', one=True)['c']:
            seed_path = os.path.join(ROOT, 'database', 'seeds', 'seed_data.py')
            if os.path.exists(seed_path):
                exec(open(seed_path).read())
                print('[db] seeded.')
    except Exception as _e:
        print(f'[db] seed check ERROR: {_e!r}')

def _start_scheduler():
    """Start APScheduler — auto-syncs Monday, sends reports, daily notifications."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        import requests as _req

        def _send_hourly_report():
            try:
                secret = os.environ.get('CRON_SECRET', 'odessa-cron-2026')
                _req.post(
                    'http://localhost:{}/api/cron/hourly-report'.format(
                        os.environ.get('PORT', 5050)
                    ),
                    json={'secret': secret},
                    headers={'X-Cron-Secret': secret},
                    timeout=30
                )
            except Exception as e:
                print(f'[scheduler] hourly report error: {e}')

        def _daily_notifications():
            try:
                from src.notifications import run_daily_checks
                run_daily_checks()
                print('[scheduler] daily notifications sent')
            except Exception as e:
                print(f'[scheduler] daily notifications error: {e}')

        def _auto_sync_monday():
            """Auto-sync apartments from Monday every 30 minutes."""
            try:
                from src.monday_sync import sync_to_db
                result = sync_to_db()
                print(f'[scheduler] Monday auto-sync: {result.get("synced")} apts, '
                      f'{result.get("updated")} updated, {result.get("created")} new')
            except Exception as e:
                print(f'[scheduler] Monday auto-sync error: {e}')

        def _auto_sync_professionals():
            """Auto-sync professionals from Monday every 2 hours."""
            try:
                from src.routes.professionals import run_professionals_sync
                result = run_professionals_sync()
                print(f'[scheduler] Professionals auto-sync: {result}')
            except Exception as e:
                print(f'[scheduler] Professionals auto-sync error: {e}')

        scheduler = BackgroundScheduler(timezone='Europe/Kiev')

        # Hourly WhatsApp report — disabled per David's request
        # scheduler.add_job(_send_hourly_report, CronTrigger(minute=2), id='hourly_report')
        # Daily notifications at 9:02 AM Odessa time
        scheduler.add_job(_daily_notifications, CronTrigger(hour=9, minute=2), id='daily_checks')
        # Auto-sync apartments from Monday every 30 minutes
        scheduler.add_job(_auto_sync_monday, IntervalTrigger(minutes=30), id='monday_sync',
                          next_run_time=__import__('datetime').datetime.now())  # run immediately on start
        # Auto-sync professionals from Monday every 2 hours
        scheduler.add_job(_auto_sync_professionals, IntervalTrigger(hours=2), id='pros_sync')

        def _sync_pending_templates():
            """Sync status of PENDING WA templates from Meta every 5 minutes."""
            try:
                from src.routes.wa_templates import sync_all_templates
                from flask import current_app
                with app.app_context():
                    from src.models import query_db as _qdb, execute_db as _edb
                    from src.routes.wa_templates import _sync_status_from_meta
                    pending = _qdb("SELECT * FROM wa_templates WHERE status IN ('pending', 'draft')")
                    for row in pending:
                        result = _sync_status_from_meta(row['name'], row.get('meta_template_id'))
                        if result and result['status'] != row['status']:
                            _edb('UPDATE wa_templates SET status=?, meta_template_id=?, rejection_reason=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                                 (result['status'], result['meta_id'], result.get('rejection_reason', ''), row['id']))
                            print(f'[scheduler] template {row["name"]} → {result["status"]}')
            except Exception as e:
                print(f'[scheduler] template sync error: {e}')

        scheduler.add_job(_sync_pending_templates, IntervalTrigger(minutes=5), id='template_sync')

        scheduler.start()
        print('[scheduler] started — Monday sync every 30min, pros every 2h, daily checks 09:02')
    except Exception as e:
        print(f'[scheduler] failed to start: {e}')


# Start scheduler once (not in debug reloader child process)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    _start_scheduler()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Starting server at http://localhost:{port}")
    app.run(debug=True, port=port)
