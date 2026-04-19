"""Role-based auth: owner (full access) and manager (read + limited write)."""
import os
import hashlib
from flask import request, Response, redirect, make_response, render_template_string

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login — Apartment Management</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #fafbfc; font-family: Inter, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #fff; border: 1px solid #ebedf0; border-radius: 12px; padding: 40px; width: 340px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
  h2 { font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #0f1419; }
  p { font-size: 13px; color: #8b95a1; margin-bottom: 28px; }
  label { font-size: 13px; font-weight: 500; color: #56606b; display: block; margin-bottom: 6px; }
  input { width: 100%; padding: 10px 14px; border: 1px solid #d8dce3; border-radius: 8px; font-size: 15px; outline: none; }
  input:focus { border-color: #5e6ad2; box-shadow: 0 0 0 3px rgba(94,106,210,0.12); }
  button { width: 100%; margin-top: 18px; padding: 11px; background: #5e6ad2; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:hover { background: #4651b8; }
  .err { margin-top: 14px; color: #ef4444; font-size: 13px; text-align: center; }
</style>
</head>
<body>
<div class="card">
  <h2>Apartment Management</h2>
  <p>Odessa properties dashboard</p>
  <form method="POST" action="/login">
    <label>Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password" placeholder="Enter password">
    <button type="submit">Sign in</button>
    {% if error %}<div class="err">Wrong password, try again</div>{% endif %}
  </form>
</div>
</body>
</html>'''

def _get_passwords():
    """Returns (owner_pw, manager_pw). Falls back to .env file."""
    owner_pw = os.environ.get('APP_PASSWORD', '')
    manager_pw = os.environ.get('MANAGER_PASSWORD', '')
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if (not owner_pw or not manager_pw) and os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith('APP_PASSWORD=') and not owner_pw:
                owner_pw = line.split('=', 1)[1].strip()
            if line.startswith('MANAGER_PASSWORD=') and not manager_pw:
                manager_pw = line.split('=', 1)[1].strip()
    return owner_pw, manager_pw

def _get_app_password():
    owner_pw, _ = _get_passwords()
    return owner_pw

def _make_cookie(role, password):
    return hashlib.sha256(f'apt-mgmt-{role}-{password}'.encode()).hexdigest()[:32]

def get_current_role():
    """Returns 'owner', 'manager', or None."""
    owner_pw, manager_pw = _get_passwords()
    if not owner_pw:
        return 'owner'  # No auth configured — full access in dev
    cookie = request.cookies.get('auth', '')
    if cookie == _make_cookie('owner', owner_pw):
        return 'owner'
    if manager_pw and cookie == _make_cookie('manager', manager_pw):
        return 'manager'
    return None

def _is_authed():
    return get_current_role() is not None

def _is_owner():
    return get_current_role() == 'owner'

# Paths accessible without any login
PUBLIC_PATHS = ['/api/whatsapp-query', '/whatsapp-bot.js', '/login', '/api/sync/push']

# Paths that require owner role (managers get 403)
OWNER_ONLY_RULES = [
    ('DELETE', '/api/tasks/'),
    ('DELETE', '/api/properties/'),
    ('DELETE', '/api/apartments/'),
    ('DELETE', '/api/tenants/'),
    ('DELETE', '/api/leases/'),
    ('DELETE', '/api/owners/'),
    ('POST',   '/api/properties'),
    ('POST',   '/api/owners'),
    ('POST',   '/api/sync'),
    # Wallets + expenses: owner only for write
    ('POST',   '/api/transactions'),
    ('PUT',    '/api/transactions/'),
    ('DELETE', '/api/transactions/'),
    ('PUT',    '/api/commission/'),
    ('POST',   '/api/expenses'),
    ('PUT',    '/api/expenses/'),
    ('DELETE', '/api/expenses/'),
]

def _is_owner_only_path(method, path):
    for m, prefix in OWNER_ONLY_RULES:
        if method == m and path.startswith(prefix):
            return True
    return False

def init_auth(app):
    @app.route('/login', methods=['GET'])
    def login_page():
        if _is_authed():
            return redirect('/')
        return render_template_string(LOGIN_HTML, error=False)

    @app.route('/login', methods=['POST'])
    def login_post():
        owner_pw, manager_pw = _get_passwords()
        entered = request.form.get('password', '')
        if entered == owner_pw:
            resp = make_response(redirect('/'))
            resp.set_cookie('auth', _make_cookie('owner', owner_pw),
                            max_age=60*60*24*30, httponly=True, samesite='Lax')
            return resp
        if manager_pw and entered == manager_pw:
            resp = make_response(redirect('/'))
            resp.set_cookie('auth', _make_cookie('manager', manager_pw),
                            max_age=60*60*24*30, httponly=True, samesite='Lax')
            return resp
        return render_template_string(LOGIN_HTML, error=True)

    @app.before_request
    def require_login():
        if request.path in PUBLIC_PATHS:
            return
        if not _is_authed():
            if request.path.startswith('/api/'):
                from flask import jsonify
                return jsonify({'error': 'Not authenticated'}), 401
            return redirect('/login')
        # Owner-only check
        if _is_owner_only_path(request.method, request.path) and not _is_owner():
            from flask import jsonify
            return jsonify({'error': 'Owner access required'}), 403
