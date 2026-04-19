"""Role-based auth: owner (env-var) + multi-user DB accounts."""
import os
import hashlib
import json
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
  label { font-size: 13px; font-weight: 500; color: #56606b; display: block; margin-bottom: 6px; margin-top: 14px; }
  input { width: 100%; padding: 10px 14px; border: 1px solid #d8dce3; border-radius: 8px; font-size: 15px; outline: none; }
  input:focus { border-color: #5e6ad2; box-shadow: 0 0 0 3px rgba(94,106,210,0.12); }
  button { width: 100%; margin-top: 20px; padding: 11px; background: #5e6ad2; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:hover { background: #4651b8; }
  .err { margin-top: 14px; color: #ef4444; font-size: 13px; text-align: center; }
  .hint { margin-top: 10px; font-size: 11px; color: #b0b8c1; text-align: center; }
</style>
</head>
<body>
<div class="card">
  <h2>Apartment Management</h2>
  <p>Odessa properties dashboard</p>
  <form method="POST" action="/login">
    <label>Username <span style="color:#b0b8c1;font-weight:400">(leave blank for owner login)</span></label>
    <input type="text" name="username" autocomplete="username" placeholder="username">
    <label>Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password" placeholder="Enter password">
    <button type="submit">Sign in</button>
    {% if error %}<div class="err">Wrong username or password</div>{% endif %}
    <div class="hint">Owner login: leave username blank</div>
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
    """Legacy cookie for env-var auth."""
    return hashlib.sha256(f'apt-mgmt-{role}-{password}'.encode()).hexdigest()[:32]


def _make_user_cookie(uid, username, password_hash):
    """DB-user cookie: u{uid}:{32-char token}."""
    token = hashlib.sha256(f'apt-mgmt-u{uid}-{username}-{password_hash}'.encode()).hexdigest()[:32]
    return f'u{uid}:{token}'


def _hash_password(password):
    return hashlib.sha256(('apt-mgmt-user-' + password).encode()).hexdigest()


def _validate_user_cookie(cookie):
    """Validate a DB-user cookie. Returns user dict or None."""
    if not cookie.startswith('u'):
        return None
    try:
        prefix, token = cookie.split(':', 1)
        uid = int(prefix[1:])
    except Exception:
        return None
    from src.models import query_db
    user = query_db(
        'SELECT * FROM app_users WHERE id = ? AND is_active = 1',
        (uid,), one=True
    )
    if not user:
        return None
    expected = hashlib.sha256(
        f'apt-mgmt-u{uid}-{user["username"]}-{user["password_hash"]}'.encode()
    ).hexdigest()[:32]
    if token == expected:
        return user
    return None


def get_current_user():
    """Returns full user dict for DB users, or synthetic dict for env-var users, or None."""
    cookie = request.cookies.get('auth', '')
    if not cookie:
        owner_pw, _ = _get_passwords()
        if not owner_pw:
            # Dev mode — no auth configured
            return {'role': 'owner', 'display_name': 'Owner', 'permissions': '{}', 'property_ids': '[]', 'is_owner': True}
        return None

    # Try DB user cookie first
    if cookie.startswith('u'):
        user = _validate_user_cookie(cookie)
        if user:
            user['is_owner'] = (user['role'] == 'owner')
            return user
        return None

    # Legacy env-var cookie
    owner_pw, manager_pw = _get_passwords()
    if not owner_pw:
        return {'role': 'owner', 'display_name': 'Owner', 'permissions': '{}', 'property_ids': '[]', 'is_owner': True}
    if cookie == _make_cookie('owner', owner_pw):
        return {'role': 'owner', 'display_name': 'Owner', 'permissions': '{}', 'property_ids': '[]', 'is_owner': True}
    if manager_pw and cookie == _make_cookie('manager', manager_pw):
        return {'role': 'admin', 'display_name': 'Admin', 'permissions': '{}', 'property_ids': '[]', 'is_owner': False}
    return None


def get_current_role():
    """Returns role string or None. Kept for backward compat."""
    user = get_current_user()
    return user['role'] if user else None


def _is_authed():
    return get_current_user() is not None


def _is_owner():
    user = get_current_user()
    return user is not None and user.get('role') == 'owner'


# Paths accessible without any login
PUBLIC_PATHS = ['/api/whatsapp-query', '/api/whatsapp/webhook', '/whatsapp-bot.js', '/login', '/api/sync/push']

# Paths that require owner role
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
    ('POST',   '/api/transactions'),
    ('PUT',    '/api/transactions/'),
    ('DELETE', '/api/transactions/'),
    ('PUT',    '/api/commission/'),
    ('POST',   '/api/expenses'),
    ('PUT',    '/api/expenses/'),
    ('DELETE', '/api/expenses/'),
    # User management — owner only
    ('GET',    '/api/users'),
    ('POST',   '/api/users'),
    ('PUT',    '/api/users/'),
    ('DELETE', '/api/users/'),
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
        username = request.form.get('username', '').strip().lower()
        entered_pw = request.form.get('password', '')

        # DB user login (username provided)
        if username:
            from src.models import query_db
            user = query_db(
                'SELECT * FROM app_users WHERE username = ? AND is_active = 1',
                (username,), one=True
            )
            if user and user['password_hash'] == _hash_password(entered_pw):
                cookie_val = _make_user_cookie(user['id'], user['username'], user['password_hash'])
                resp = make_response(redirect('/'))
                resp.set_cookie('auth', cookie_val, max_age=60*60*24*30, httponly=True, samesite='Lax')
                return resp
            return render_template_string(LOGIN_HTML, error=True)

        # Legacy env-var login (no username — owner/manager)
        owner_pw, manager_pw = _get_passwords()
        if entered_pw == owner_pw:
            resp = make_response(redirect('/'))
            resp.set_cookie('auth', _make_cookie('owner', owner_pw),
                            max_age=60*60*24*30, httponly=True, samesite='Lax')
            return resp
        if manager_pw and entered_pw == manager_pw:
            resp = make_response(redirect('/'))
            resp.set_cookie('auth', _make_cookie('manager', manager_pw),
                            max_age=60*60*24*30, httponly=True, samesite='Lax')
            return resp
        return render_template_string(LOGIN_HTML, error=True)

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        resp = make_response(redirect('/login'))
        resp.set_cookie('auth', '', max_age=0)
        return resp

    @app.before_request
    def require_login():
        if request.path in PUBLIC_PATHS:
            return
        if not _is_authed():
            if request.path.startswith('/api/'):
                from flask import jsonify
                return jsonify({'error': 'Not authenticated'}), 401
            return redirect('/login')
        if _is_owner_only_path(request.method, request.path) and not _is_owner():
            from flask import jsonify
            return jsonify({'error': 'Owner access required'}), 403
