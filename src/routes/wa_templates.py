"""WA Templates — create, manage and send WhatsApp Message Templates via Meta API."""
import os
import json
import requests as _req
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db, get_setting, set_setting

bp = Blueprint('wa_templates', __name__)

WA_API_URL = 'https://graph.facebook.com/v19.0'


def _token():
    from src.models import get_setting as gs
    return gs('whatsapp_token') or os.environ.get('WHATSAPP_TOKEN', '')


def _phone_id():
    from src.models import get_setting as gs
    return gs('whatsapp_phone_id') or os.environ.get('WHATSAPP_PHONE_ID', '')


def _get_waba_id():
    """Auto-discover and cache WABA_ID from Phone Number ID."""
    cached = get_setting('waba_id')
    if cached:
        return cached
    phone_id = _phone_id()
    token = _token()
    if not phone_id or not token:
        return None
    try:
        r = _req.get(f'{WA_API_URL}/{phone_id}',
                     headers={'Authorization': f'Bearer {token}'}, timeout=10)
        data = r.json()
        waba_id = data.get('account_id') or data.get('whatsapp_business_account_id')
        if waba_id:
            set_setting('waba_id', str(waba_id))
            return str(waba_id)
    except Exception as e:
        print(f'[wa_templates] WABA_ID discovery error: {e}')
    return None


def _row_to_dict(row):
    if not row:
        return row
    r = dict(row)
    try:
        r['components'] = json.loads(r['components']) if r.get('components') else []
    except Exception:
        r['components'] = []
    return r


def _sync_status_from_meta(template_name, meta_id=None):
    """Pull latest status for a template from Meta API. Returns dict or None."""
    waba_id = _get_waba_id()
    token = _token()
    if not waba_id or not token:
        return None
    try:
        url = f'{WA_API_URL}/{waba_id}/message_templates'
        params = {'fields': 'name,status,rejection_reason,id', 'limit': 100}
        if meta_id:
            params['name'] = template_name
        r = _req.get(url, params=params,
                     headers={'Authorization': f'Bearer {token}'}, timeout=15)
        data = r.json()
        templates = data.get('data', [])
        for t in templates:
            if t.get('name') == template_name or (meta_id and str(t.get('id')) == str(meta_id)):
                return {
                    'status': t.get('status', '').lower(),
                    'meta_id': str(t.get('id', '')),
                    'rejection_reason': t.get('rejection_reason', ''),
                }
    except Exception as e:
        print(f'[wa_templates] sync error: {e}')
    return None


# ── WABA ID discovery endpoint ──────────────────────────────────────────────
@bp.route('/api/wa/waba-id', methods=['GET'])
def get_waba_id():
    wid = _get_waba_id()
    if wid:
        return jsonify({'waba_id': wid})
    return jsonify({'error': 'Could not discover WABA_ID'}), 500


# ── List templates ──────────────────────────────────────────────────────────
@bp.route('/api/wa/templates', methods=['GET'])
def list_templates():
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    q = 'SELECT * FROM wa_templates WHERE 1=1'
    args = []
    if status:
        q += ' AND status = ?'
        args.append(status)
    if category:
        q += ' AND category = ?'
        args.append(category)
    q += ' ORDER BY created_at DESC'
    rows = query_db(q, args)
    return jsonify([_row_to_dict(r) for r in rows])


# ── Get single template ─────────────────────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>', methods=['GET'])
def get_template(tid):
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(_row_to_dict(row))


# ── Create template ─────────────────────────────────────────────────────────
@bp.route('/api/wa/templates', methods=['POST'])
def create_template():
    d = request.json or {}
    name = (d.get('name') or '').strip().lower().replace(' ', '_')
    if not name:
        return jsonify({'error': 'name required'}), 400
    category = d.get('category', 'UTILITY').upper()
    language = d.get('language', 'ru')
    components = d.get('components', [])
    status = 'draft'

    nid = insert_db(
        'INSERT INTO wa_templates (name, category, language, status, components) VALUES (?, ?, ?, ?, ?)',
        (name, category, language, status, json.dumps(components, ensure_ascii=False))
    )
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (nid,), one=True)
    return jsonify(_row_to_dict(row)), 201


# ── Update template (draft only) ────────────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>', methods=['PUT'])
def update_template(tid):
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    d = request.json or {}
    name = (d.get('name') or row['name']).strip().lower().replace(' ', '_')
    execute_db(
        '''UPDATE wa_templates SET name=?, category=?, language=?, components=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (name, d.get('category', row['category']).upper(),
         d.get('language', row['language']),
         json.dumps(d.get('components', json.loads(row['components'] or '[]')), ensure_ascii=False),
         tid)
    )
    updated = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    return jsonify(_row_to_dict(updated))


# ── Delete template ─────────────────────────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>', methods=['DELETE'])
def delete_template(tid):
    execute_db('DELETE FROM wa_templates WHERE id = ?', (tid,))
    return jsonify({'ok': True})


# ── Submit to Meta for approval ─────────────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>/submit', methods=['POST'])
def submit_template(tid):
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404

    waba_id = _get_waba_id()
    token = _token()
    if not waba_id or not token:
        return jsonify({'error': 'WhatsApp credentials not configured (WABA_ID or token missing)'}), 500

    components = json.loads(row['components'] or '[]')
    payload = {
        'name': row['name'],
        'language': row['language'],
        'category': row['category'],
        'components': components,
    }

    try:
        r = _req.post(
            f'{WA_API_URL}/{waba_id}/message_templates',
            json=payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=20
        )
        resp = r.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if 'error' in resp:
        err_msg = resp['error'].get('message', str(resp['error']))
        return jsonify({'error': err_msg, 'meta_response': resp}), 400

    meta_id = str(resp.get('id', ''))
    new_status = resp.get('status', 'PENDING').lower()

    execute_db(
        'UPDATE wa_templates SET status=?, meta_template_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
        (new_status, meta_id, tid)
    )
    updated = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    return jsonify({**_row_to_dict(updated), 'meta_response': resp})


# ── Sync status from Meta ───────────────────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>/sync-status', methods=['POST'])
def sync_template_status(tid):
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    result = _sync_status_from_meta(row['name'], row.get('meta_template_id'))
    if not result:
        return jsonify({'error': 'Could not fetch status from Meta'}), 500
    execute_db(
        'UPDATE wa_templates SET status=?, meta_template_id=?, rejection_reason=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
        (result['status'], result['meta_id'], result.get('rejection_reason', ''), tid)
    )
    updated = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    return jsonify(_row_to_dict(updated))


# ── Sync all PENDING templates ──────────────────────────────────────────────
@bp.route('/api/wa/templates/sync-all', methods=['POST'])
def sync_all_templates():
    pending = query_db("SELECT * FROM wa_templates WHERE status IN ('pending', 'draft')")
    updated_count = 0
    for row in pending:
        result = _sync_status_from_meta(row['name'], row.get('meta_template_id'))
        if result and result['status'] != row['status']:
            execute_db(
                'UPDATE wa_templates SET status=?, meta_template_id=?, rejection_reason=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (result['status'], result['meta_id'], result.get('rejection_reason', ''), row['id'])
            )
            updated_count += 1
    return jsonify({'ok': True, 'updated': updated_count})


# ── Send approved template to a contact ────────────────────────────────────
@bp.route('/api/wa/templates/<int:tid>/send', methods=['POST'])
def send_template(tid):
    row = query_db('SELECT * FROM wa_templates WHERE id = ?', (tid,), one=True)
    if not row:
        return jsonify({'error': 'not found'}), 404
    if row['status'] not in ('approved', 'APPROVED'):
        return jsonify({'error': f'Template status is {row["status"]}, must be approved'}), 400

    d = request.json or {}
    to_phone = (d.get('phone') or '').strip()
    parameters = d.get('parameters', {})  # {key: value} mapping
    frequency = d.get('frequency', 'one-time')
    schedule_date = d.get('schedule_date', '')

    if not to_phone:
        return jsonify({'error': 'phone required'}), 400

    token = _token()
    phone_id = _phone_id()
    if not token or not phone_id:
        return jsonify({'error': 'WhatsApp credentials not configured'}), 500

    # Build Meta send payload
    components = json.loads(row['components'] or '[]')
    send_components = []
    for comp in components:
        ctype = comp.get('type', '').lower()
        if ctype == 'header':
            fmt = comp.get('format', 'TEXT').upper()
            if fmt == 'TEXT' and comp.get('text'):
                text = comp['text']
                for k, v in parameters.items():
                    text = text.replace(f'{{{{{k}}}}}', str(v))
                send_components.append({
                    'type': 'header',
                    'parameters': [{'type': 'text', 'text': text}]
                })
            elif fmt == 'IMAGE' and comp.get('example', {}).get('header_handle'):
                send_components.append({
                    'type': 'header',
                    'parameters': [{'type': 'image', 'image': {'link': comp['example']['header_handle'][0]}}]
                })
        elif ctype == 'body':
            text = comp.get('text', '')
            # Collect positional variables {{1}}, {{2}}, ...
            import re
            vars_in_text = re.findall(r'\{\{(\d+)\}\}', text)
            if vars_in_text:
                # parameters can be list or dict with positional keys
                params_list = d.get('body_params', [])
                if params_list:
                    send_components.append({
                        'type': 'body',
                        'parameters': [{'type': 'text', 'text': str(p)} for p in params_list]
                    })
        elif ctype == 'button':
            for i, btn in enumerate(comp.get('buttons', [])):
                if btn.get('type') == 'URL' and '{{1}}' in btn.get('url', ''):
                    url_param = parameters.get('url_param', '')
                    send_components.append({
                        'type': 'button', 'sub_type': 'url', 'index': i,
                        'parameters': [{'type': 'text', 'text': url_param}]
                    })

    meta_payload = {
        'messaging_product': 'whatsapp',
        'to': to_phone,
        'type': 'template',
        'template': {
            'name': row['name'],
            'language': {'code': row['language']},
        }
    }
    if send_components:
        meta_payload['template']['components'] = send_components

    try:
        r = _req.post(
            f'{WA_API_URL}/{phone_id}/messages',
            json=meta_payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=15
        )
        resp = r.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    status = 'sent' if 'messages' in resp else 'failed'
    contact = query_db('SELECT name FROM wa_contacts WHERE phone = ?', (to_phone,), one=True)
    contact_name = (contact or {}).get('name', to_phone)

    insert_db(
        '''INSERT INTO wa_template_sends
           (template_id, template_name, contact_phone, contact_name, parameters, frequency, schedule_date, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (tid, row['name'], to_phone, contact_name,
         json.dumps(parameters, ensure_ascii=False), frequency, schedule_date, status)
    )

    if 'error' in resp:
        return jsonify({'error': resp['error'].get('message'), 'meta_response': resp}), 400
    return jsonify({'ok': True, 'status': status, 'meta_response': resp})


# ── Send log ────────────────────────────────────────────────────────────────
@bp.route('/api/wa/send-log', methods=['GET'])
def send_log():
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    template_id = request.args.get('template_id')
    phone = request.args.get('phone', '')

    q = 'SELECT * FROM wa_template_sends WHERE 1=1'
    args = []
    if template_id:
        q += ' AND template_id = ?'
        args.append(template_id)
    if phone:
        q += ' AND contact_phone LIKE ?'
        args.append(f'%{phone}%')

    total = (query_db(q.replace('SELECT *', 'SELECT COUNT(*) as c'), args, one=True) or {}).get('c', 0)
    q += ' ORDER BY sent_at DESC LIMIT ? OFFSET ?'
    args.extend([limit, offset])
    rows = query_db(q, args)
    result = []
    for r in rows:
        r = dict(r)
        try:
            r['parameters'] = json.loads(r['parameters']) if r.get('parameters') else {}
        except Exception:
            r['parameters'] = {}
        result.append(r)
    return jsonify({'entries': result, 'total': total, 'offset': offset, 'limit': limit})
