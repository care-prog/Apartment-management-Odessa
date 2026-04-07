"""Simple password protection for the dashboard."""
import os
from functools import wraps
from flask import request, Response

def check_auth(password):
    app_password = os.environ.get('APP_PASSWORD', '')
    if not app_password:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith('APP_PASSWORD='):
                    app_password = line.split('=', 1)[1].strip()
    if not app_password:
        return True  # No password set = no auth required (local dev)
    return password == app_password

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not check_auth(auth.password if auth else ''):
            return Response('Login required', 401, {'WWW-Authenticate': 'Basic realm="Apartment Management Odessa"'})
        return f(*args, **kwargs)
    return decorated

def init_auth(app):
    @app.before_request
    def require_login():
        if request.path.startswith('/api/') or request.path == '/' or request.path.endswith('.html') or request.path.endswith('.css') or request.path.endswith('.js'):
            auth = request.authorization
            if not check_auth(auth.password if auth else ''):
                return Response('Login required', 401, {'WWW-Authenticate': 'Basic realm="Apartment Management Odessa"'})
