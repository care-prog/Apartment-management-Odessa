"""
WhatsApp API — handles both ManyChat relay and official Meta WhatsApp webhook.
Official Meta webhook: GET /api/whatsapp/webhook (verify) + POST (incoming messages)
ManyChat relay (legacy): POST /api/whatsapp-query
"""
import os
import re
import json
import requests as _requests
from flask import Blueprint, request, jsonify
from src.models import query_db

bp = Blueprint('whatsapp', __name__)


def normalize_phone(phone):
    """Normalize phone to digits only, strip leading + and country code variations."""
    if not phone:
        return ''
    digits = re.sub(r'\D', '', phone)
    return digits


def identify_sender(phone):
    """Returns ('team'|'property_owner'|'tenant'|'unknown', user_data)."""
    p = normalize_phone(phone)
    if not p:
        return ('unknown', None)

    # Try team members first
    team = query_db("SELECT * FROM team_members WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') = ?", (p,), one=True)
    if team:
        role = team.get('role', 'manager')
        # property_owner gets their own role, everyone else is 'team'
        if role == 'property_owner':
            # Enrich with their properties from owners table
            owner = query_db(
                "SELECT * FROM owners WHERE REPLACE(REPLACE(REPLACE(contact, '+', ''), '-', ''), ' ', '') = ?",
                (p,), one=True
            )
            user = dict(team)
            if owner:
                user['owner_id'] = owner['id']
                props = query_db(
                    'SELECT id, name, address FROM properties WHERE owner_id = ?',
                    (owner['id'],)
                )
                user['properties'] = [dict(pr) for pr in props]
            else:
                user['owner_id'] = None
                user['properties'] = []
            return ('property_owner', user)
        return ('team', team)

    # Try tenants
    tenant = query_db("""
        SELECT t.*, l.id as lease_id, l.rent_amount, l.start_date, l.end_date,
               a.number as apt_number, a.notes as apt_notes,
               p.name as property_name, p.address as property_address
        FROM tenants t
        LEFT JOIN leases l ON t.id = l.tenant_id AND l.status = 'active'
        LEFT JOIN apartments a ON l.apartment_id = a.id
        LEFT JOIN properties p ON a.property_id = p.id
        WHERE REPLACE(REPLACE(REPLACE(t.phone, '+', ''), '-', ''), ' ', '') = ?
    """, (p,), one=True)
    if tenant:
        return ('tenant', tenant)

    return ('unknown', None)


def extract_apt_number(text):
    """Extract apartment number from text. Looks for digits 1-3 long, possibly with /."""
    if not text:
        return None
    # Look for explicit "квартира", "דירה", "apt", "flat", or just numbers
    match = re.search(r'(?:квартир[ауы]?|דירה|apt|flat|кв\.?|#)\s*(\d+(?:/\d+)?)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Standalone number 1-4 digits
    match = re.search(r'\b(\d{1,4}(?:/\d+)?)\b', text)
    if match:
        return match.group(1)
    return None


def find_apartment(apt_number):
    """Find apartment by number. Returns apartment with lease + tenant info."""
    if not apt_number:
        return None
    rows = query_db("""
        SELECT a.*, p.name as property_name, p.address as property_address,
               o.name as owner_name,
               l.id as lease_id, l.rent_amount, l.start_date, l.end_date,
               t.name as tenant_name, t.phone as tenant_phone
        FROM apartments a
        JOIN properties p ON a.property_id = p.id
        LEFT JOIN owners o ON p.owner_id = o.id
        LEFT JOIN leases l ON l.apartment_id = a.id AND l.status = 'active'
        LEFT JOIN tenants t ON l.tenant_id = t.id
        WHERE a.number = ?
    """, (apt_number,))
    return rows[0] if rows else None


def parse_apt_notes(notes_str):
    """Parse Monday.com data stored in apartments.notes JSON field."""
    try:
        return json.loads(notes_str or '{}')
    except:
        return {}


def format_team_response(apt, lang='ru'):
    """Full apartment info for team members."""
    notes = parse_apt_notes(apt.get('apt_notes') or apt.get('notes'))
    lines = []
    lines.append(f"🏠 *{apt['property_name']} #{apt['number']}*")
    if apt.get('property_address'):
        lines.append(f"📍 {apt['property_address']}")
    if apt.get('owner_name'):
        lines.append(f"👤 בעלים: {apt['owner_name']}")
    lines.append("")
    lines.append(f"📊 סטטוס: {apt['status']}")
    if apt.get('monthly_rent'):
        lines.append(f"💰 שכירות: ${apt['monthly_rent']}")

    if apt.get('tenant_name') and 'Tenant' not in apt['tenant_name']:
        lines.append(f"👥 דייר: {apt['tenant_name']}")
        if apt.get('tenant_phone'):
            lines.append(f"📞 {apt['tenant_phone']}")

    if apt.get('start_date'):
        lines.append(f"📅 התחלת חוזה: {apt['start_date']}")
    if apt.get('end_date'):
        lines.append(f"📅 סוף חוזה: {apt['end_date']}")

    if notes.get('timeline'):
        lines.append(f"💳 תשלום שכירות: {notes['timeline']}")
    if notes.get('meters'):
        lines.append(f"📐 מטרז': {notes['meters']} מ\"ר")
    if notes.get('code_box'):
        lines.append(f"🔐 Code box: {notes['code_box']}")
    if notes.get('wifi_paid'):
        lines.append(f"📶 WiFi: {notes['wifi_paid']}")

    return '\n'.join(lines)


def format_tenant_response(tenant, message, lang='ru'):
    """Limited info for tenants - only what they should know about THEIR apartment."""
    msg_lower = (message or '').lower()
    lines = []

    # Greeting
    name = tenant.get('name', '')
    if not name.startswith('Tenant'):
        lines.append(f"שלום {name}! 👋")
    else:
        lines.append("שלום! 👋")
    lines.append("")

    notes = parse_apt_notes(tenant.get('apt_notes'))

    # Match their question topic
    asked_about = []

    if any(w in msg_lower for w in ['rent', 'оплат', 'плат', 'שכר', 'שכירות', 'pay', 'אמור לשלם', 'how much']):
        asked_about.append('rent')
    if any(w in msg_lower for w in ['lease', 'contract', 'חוזה', 'договор', 'когда конч', 'кончается']):
        asked_about.append('lease')
    if any(w in msg_lower for w in ['wifi', 'internet', 'интернет', 'אינטרנט', 'pass', 'пароль']):
        asked_about.append('wifi')
    if any(w in msg_lower for w in ['key', 'ключ', 'מפת', 'code', 'код']):
        asked_about.append('access')
    if any(w in msg_lower for w in ['repair', 'broke', 'חבל', 'сломал', 'не работает', 'תיקון', 'maintenance']):
        asked_about.append('maintenance')

    # Default: brief overview
    if not asked_about:
        asked_about = ['overview']

    if 'overview' in asked_about or 'rent' in asked_about:
        lines.append(f"🏠 הדירה שלך: *{tenant.get('property_name', '')} #{tenant.get('apt_number', '')}*")
        if tenant.get('rent_amount'):
            lines.append(f"💰 שכירות חודשית: ${tenant['rent_amount']}")
        if notes.get('timeline'):
            parts = notes['timeline'].split(' - ')
            if len(parts) == 2:
                lines.append(f"📅 התשלום הבא צריך להיות עד: {parts[1]}")

    if 'lease' in asked_about and tenant.get('end_date'):
        lines.append(f"📄 החוזה שלך מסתיים: {tenant['end_date']}")

    if 'wifi' in asked_about:
        # Extract wifi info from internet field if present
        internet = notes.get('internet', '')
        if internet:
            lines.append(f"📶 פרטי WiFi:\n{internet[:300]}")
        else:
            lines.append("📶 פרטי ה-WiFi נמצאים בחוזה שלך. אם איבדת — תכתוב למנהלת.")

    if 'access' in asked_about:
        if notes.get('code_box'):
            lines.append(f"🔐 קוד הכניסה לקופסת המפתחות: {notes['code_box']}")
        else:
            lines.append("🔑 לקבלת מפתחות/קודי כניסה — תכתוב למנהלת.")

    if 'maintenance' in asked_about:
        lines.append("🔧 לבקשת תיקון — תכתוב לי את הבעיה ותצרף תמונה אם אפשר. המנהלת תיצור איתך קשר.")

    lines.append("")
    lines.append("_איך אני יכולה לעזור עוד?_")

    return '\n'.join(lines)


def format_unknown_response(message, message_lower):
    """Response for unknown senders - ask which apartment they're asking about."""
    apt = extract_apt_number(message)
    if apt:
        return ("שלום! 👋\nלא הצלחתי לזהות אותך במערכת. "
                f"אני רואה שאתה שואל על דירה {apt}. "
                "כדי שאוכל לעזור לך, אנא תאשר את הזהות שלך:\n"
                "האם אתה הדייר של הדירה? אם כן, איך קוראים לך?")
    return ("שלום! 👋\nאני העוזרת הוירטואלית של ניהול הדירות באודסה. "
            "כדי שאוכל לעזור — תגיד לי בבקשה איזה דירה אתה שואל עליה (מספר דירה).")


import time as _time

# ── In-memory session state per phone ──
# WA_SESSIONS[phone] = {'history': [...], 'last_activity': timestamp}
WA_SESSIONS = {}
WA_MAX_HISTORY = 20
SESSION_TIMEOUT_SECONDS = 300  # 5 minutes

SESSION_TIMEOUT_SECONDS = 1800  # 30 minutes idle = new session


# ── Meta WhatsApp Cloud API ──────────────────────────────────────────────────

WA_PHONE_ID   = os.environ.get('WHATSAPP_PHONE_ID', '')
WA_TOKEN      = os.environ.get('WHATSAPP_TOKEN', '')
WA_VERIFY_TOK = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'odessa-whatsapp-2026')
WA_API_URL    = 'https://graph.facebook.com/v19.0'


def _get_wa_token():
    """Get WhatsApp token — DB override takes priority over env var."""
    from src.models import get_setting
    return get_setting('whatsapp_token') or WA_TOKEN


def _get_wa_phone_id():
    """Get WhatsApp Phone Number ID — DB override takes priority over env var."""
    from src.models import get_setting
    return get_setting('whatsapp_phone_id') or WA_PHONE_ID


def wa_send(to_phone, text):
    """Send a WhatsApp text message via Meta Cloud API."""
    token   = _get_wa_token()
    phone_id = _get_wa_phone_id()
    if not phone_id or not token:
        return {'error': 'WhatsApp credentials not set'}
    url = f'{WA_API_URL}/{phone_id}/messages'
    payload = {
        'messaging_product': 'whatsapp',
        'to': to_phone,
        'type': 'text',
        'text': {'body': text[:4096]},
    }
    resp = _requests.post(url, json=payload,
                          headers={'Authorization': f'Bearer {token}',
                                   'Content-Type': 'application/json'},
                          timeout=15)
    return resp.json()


@bp.route('/api/whatsapp/webhook', methods=['GET'])
def wa_webhook_verify():
    """Meta calls this to verify the webhook. Must return hub.challenge."""
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == WA_VERIFY_TOK:
        return challenge, 200
    return 'Forbidden', 403


@bp.route('/api/whatsapp/webhook', methods=['POST'])
def wa_webhook_receive():
    """Receive incoming WhatsApp messages from Meta and reply via Claude."""
    data = request.json or {}

    try:
        entry   = (data.get('entry') or [{}])[0]
        changes = (entry.get('changes') or [{}])[0]
        value   = changes.get('value', {})

        # Only process actual messages (ignore status updates)
        messages = value.get('messages', [])
        if not messages:
            return jsonify({'status': 'ignored'}), 200

        msg       = messages[0]
        msg_type  = msg.get('type', '')
        from_phone = msg.get('from', '')  # international format, no +

        # Only handle text messages for now
        if msg_type != 'text':
            wa_send(from_phone, '⚠️ Sorry, I can only process text messages for now.')
            return jsonify({'status': 'unsupported_type'}), 200

        message_body = msg['text']['body'].strip()
        if not message_body:
            return jsonify({'status': 'empty'}), 200

        # ── Identify sender & route ───────────────────────────────────────
        from src.routes.chat import call_claude, gather_context, execute_tool, TOOLS, LANG_NAMES
        import json as _json
        import time as _time

        role, user = identify_sender(from_phone)

        # Unknown number → reject immediately, no Claude call
        if role == 'unknown':
            wa_send(from_phone,
                    "אני לא מזהה אותך במערכת.\n"
                    "I don't recognize your number in the system.\n"
                    "Please contact the system administrator. 🔒")
            return jsonify({'status': 'unknown_sender'}), 200

        # Property owner → limited access, no write tools
        if role == 'property_owner':
            role = 'property_owner'  # keep explicit

        norm_phone = normalize_phone(from_phone) or from_phone
        now = _time.time()
        session = WA_SESSIONS.get(norm_phone)
        is_new_session = (session is None or
                          (now - session.get('last_activity', 0)) >= SESSION_TIMEOUT_SECONDS)
        if is_new_session:
            WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}

        # Active session — full Claude response
        if norm_phone not in WA_SESSIONS:
            WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}
        WA_SESSIONS[norm_phone]['last_activity'] = now
        history = WA_SESSIONS[norm_phone]['history']

        user_lang  = user.get('language', 'he') if user else 'he'
        lang_name  = LANG_NAMES.get(user_lang, 'Hebrew')
        context    = gather_context()

        display_name = user.get('name') or user.get('display_name') or 'שם לא ידוע'

        if role == 'team':
            access_note = (f"This user is a TEAM MEMBER. Name: {display_name}, role: {user.get('role','')}. "
                           "Full access — answer any question, take any action.")
        elif role == 'property_owner':
            prop_names = ', '.join(p['name'] for p in (user.get('properties') or []))
            access_note = (
                f"This user is a PROPERTY OWNER. Name: {display_name}. "
                f"Their properties: {prop_names or 'none assigned yet'}. "
                "Show them: rent collection status for their units, maintenance orders on their properties, "
                "how much they are owed. "
                "Do NOT show: other owners' data, office cash, team tasks, other tenants. "
                "Do NOT use write tools (no creating tasks, no expenses)."
            )
        else:  # tenant
            apt_no = user.get('apt_number', '?')
            prop   = user.get('property_name', '')
            access_note = (f"This user is a TENANT. Name: {display_name}, renting {prop} #{apt_no}. "
                           "Only share info about THEIR apartment. NO other tenant info, NO financials.")

        greeting_instruction = (
            f"IMPORTANT: This is the FIRST message from this person in a new conversation. "
            f"Start your reply with a warm greeting: 'שלום {display_name}! 👋' "
            f"then immediately answer their question."
            if is_new_session else ""
        )

        system_prompt = f"""You are the WhatsApp assistant for "Apartment Management Odessa".
Be CONCISE — WhatsApp messages must be short. No markdown tables. Light emoji use only.
{access_note}
{greeting_instruction}
Respond in the same language the user wrote in (default: {lang_name}).

CURRENT DATA:
{_json.dumps(context, ensure_ascii=False, default=str)[:12000]}
"""
        messages_arr = []
        for h in history[-WA_MAX_HISTORY:]:
            messages_arr.append({'role': h['role'], 'content': h['content']})
        messages_arr.append({'role': 'user', 'content': message_body})

        use_tools   = (role == 'team')  # property_owner and tenant cannot trigger write actions
        actions     = []

        for _ in range(4):
            result = call_claude(messages_arr, system_prompt, use_tools=use_tools)
            if 'error' in result:
                wa_send(from_phone, '⚠️ ' + result['error'][:200])
                return jsonify({'status': 'error'}), 200

            content    = result.get('content', [])
            tool_uses  = [c for c in content if c.get('type') == 'tool_use']
            text_blocks = [c for c in content if c.get('type') == 'text']

            if not tool_uses:
                reply_text = '\n'.join(b.get('text', '') for b in text_blocks).strip()
                history.append({'role': 'user',      'content': message_body})
                history.append({'role': 'assistant', 'content': reply_text})
                WA_SESSIONS[norm_phone]['history']       = history[-WA_MAX_HISTORY:]
                WA_SESSIONS[norm_phone]['last_activity'] = _time.time()
                wa_send(from_phone, reply_text or '✓')
                return jsonify({'status': 'replied', 'actions': actions}), 200

            messages_arr.append({'role': 'assistant', 'content': content})
            tool_results = []
            for tu in tool_uses:
                tr = execute_tool(tu['name'], tu.get('input', {}))
                actions.append({'tool': tu['name'], 'result': tr})
                tool_results.append({
                    'type': 'tool_result',
                    'tool_use_id': tu['id'],
                    'content': _json.dumps(tr, ensure_ascii=False),
                })
            messages_arr.append({'role': 'user', 'content': tool_results})

        wa_send(from_phone, 'Done ✓')
        return jsonify({'status': 'done', 'actions': actions}), 200

    except Exception as e:
        # Always return 200 to Meta, even on errors — otherwise Meta retries forever
        return jsonify({'status': 'error', 'detail': str(e)}), 200


# ── Settings API (WhatsApp token + status) ─────────────────────────────────
@bp.route('/api/whatsapp/token-status', methods=['GET'])
def wa_token_status():
    """Check if the current WhatsApp token is valid."""
    token    = _get_wa_token()
    phone_id = _get_wa_phone_id()
    if not token or not phone_id:
        return jsonify({'valid': False, 'error': 'No credentials configured', 'source': 'none'})
    try:
        r = _requests.get(
            f'{WA_API_URL}/{phone_id}?fields=display_phone_number,verified_name',
            headers={'Authorization': f'Bearer {token}'}, timeout=8)
        data = r.json()
        if 'error' in data:
            return jsonify({'valid': False, 'error': data['error'].get('message', 'Token invalid'),
                            'source': 'db' if _get_wa_token() != WA_TOKEN else 'env',
                            'phone_id': phone_id})
        return jsonify({'valid': True,
                        'phone': data.get('display_phone_number',''),
                        'name': data.get('verified_name',''),
                        'source': 'db' if _get_wa_token() != WA_TOKEN else 'env',
                        'phone_id': phone_id})
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)})


@bp.route('/api/whatsapp/update-token', methods=['POST'])
def wa_update_token():
    """Owner-only: save WhatsApp token and/or Phone Number ID to DB."""
    from flask import jsonify as _j
    d = request.json or {}
    token    = (d.get('token')    or '').strip()
    phone_id = (d.get('phone_id') or '').strip()

    if not token and not phone_id:
        return _j({'error': 'token or phone_id required'}), 400

    from src.models import set_setting, get_setting

    # Phone ID only (no token change) — save without Meta validation, just a number
    if phone_id and not token:
        set_setting('whatsapp_phone_id', phone_id)
        return _j({'ok': True, 'saved_phone_id': True,
                   'note': 'Phone ID saved. Provide a token to fully validate.'})

    # Token provided — validate against Meta using new or existing phone_id
    effective_phone_id = phone_id or _get_wa_phone_id()
    try:
        r = _requests.get(
            f'{WA_API_URL}/{effective_phone_id}?fields=display_phone_number,verified_name',
            headers={'Authorization': f'Bearer {token}'}, timeout=8)
        data = r.json()
        if 'error' in data:
            return _j({'error': 'Meta rejected: ' + data['error'].get('message','')}), 400
    except Exception as e:
        return _j({'error': f'Could not verify with Meta: {e}'}), 400

    set_setting('whatsapp_token', token)
    if phone_id:
        set_setting('whatsapp_phone_id', phone_id)

    return _j({'ok': True,
               'phone': data.get('display_phone_number',''),
               'name':  data.get('verified_name',''),
               'saved_token': True,
               'saved_phone_id': bool(phone_id)})


# ── ManyChat relay (legacy) ───────────────────────────────────────────────────
@bp.route('/api/whatsapp-query', methods=['POST'])
def whatsapp_query():
    data = request.json or {}

    # Support both simple format and ManyChat Full Contact Data format
    phone = data.get('phone', '')
    message = data.get('message', '')

    # If it looks like ManyChat Full Contact Data, extract from there
    manychat_name = ''
    if 'last_input_text' in data or 'id' in data:
        message = message or data.get('last_input_text', '')
        phone = phone or data.get('phone') or data.get('whatsapp_phone') or ''
        if not phone and data.get('id'):
            phone = 'mc_' + str(data['id'])
        manychat_name = data.get('name') or data.get('first_name') or ''

    # Require at least a message — phone can be blank (we'll treat as unknown)
    if not message:
        return jsonify({'reply': '\u200b', 'role': 'error', 'silent': True})
    # Even if phone is missing, use a generic session key so the bot still works
    if not phone:
        phone = 'anon_' + (manychat_name or 'guest')

    role, user = identify_sender(phone)

    # If we didn't identify by phone but have a ManyChat name, try matching by name
    if role == 'unknown' and manychat_name:
        team = query_db("SELECT * FROM team_members WHERE LOWER(name) = LOWER(?)", (manychat_name,), one=True)
        if team:
            role, user = 'team', team
        else:
            # Also check first name
            first = manychat_name.split()[0]
            team = query_db("SELECT * FROM team_members WHERE LOWER(name) LIKE LOWER(?)", (f'{first}%',), one=True)
            if team:
                role, user = 'team', team

    norm_phone = normalize_phone(phone) or phone
    now = _time.time()

    # Unknown sender → reject
    if role == 'unknown':
        return jsonify({
            'reply': 'אני לא מזהה אותך במערכת. פנה למנהל מערכות 🔒',
            'role': 'unknown', 'silent': False
        })

    # Property owner → read-only
    if role == 'property_owner':
        role = 'property_owner'  # keep explicit for system prompt below

    # Session management
    session = WA_SESSIONS.get(norm_phone)
    is_new_session = (session is None or
                      (now - session.get('last_activity', 0)) >= SESSION_TIMEOUT_SECONDS)
    if is_new_session:
        WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}

    # Route through Claude + tools
    from src.routes.chat import call_claude, gather_context, execute_tool, TOOLS, LANG_NAMES
    import json as _json

    # Ensure session exists (edge case: trigger AND active session — pick up existing)
    if norm_phone not in WA_SESSIONS:
        WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}
    WA_SESSIONS[norm_phone]['last_activity'] = now
    history = WA_SESSIONS[norm_phone]['history']
    user_lang = user.get('language', 'he') if user else 'he'
    lang_name = LANG_NAMES.get(user_lang, 'Hebrew')

    context = gather_context()

    display_name = user.get('name') or user.get('display_name') or ''

    # Different system prompt per role
    if role == 'team':
        access_note = f"This user is a TEAM MEMBER. Name: {display_name}, role: {user.get('role','')}. Full access — answer any question, take any action."
    elif role == 'property_owner':
        prop_names = ', '.join(p['name'] for p in (user.get('properties') or []))
        access_note = (
            f"This user is a PROPERTY OWNER. Name: {display_name}. "
            f"Their properties: {prop_names or 'none assigned yet'}. "
            "Show rent status, maintenance orders, and balance owed for THEIR properties only. "
            "Do NOT show other owners' data, office cash, or team tasks. No write actions."
        )
    else:
        apt_no = user.get('apt_number', 'unknown')
        prop = user.get('property_name', '')
        access_note = (f"This user is a TENANT. Name: {display_name}, renting {prop} #{apt_no}. "
                       "ONLY share information about THEIR apartment and lease. "
                       "DO NOT use tools that modify data.")

    greeting_instruction = (
        f"IMPORTANT: This is the FIRST message from this person. "
        f"Start your reply with: 'שלום {display_name}! 👋' then answer their question."
        if is_new_session else ""
    )

    system_prompt = f"""You are the WhatsApp assistant for "Apartment Management Odessa".
Be CONCISE — WhatsApp messages should be short and clear.
No markdown headers or tables. Light emoji use.

{access_note}
{greeting_instruction}

The user's preferred language is {lang_name}. Respond in the same language they wrote in.

CURRENT DATABASE STATE:
```json
{_json.dumps(context, ensure_ascii=False, default=str, indent=1)[:15000]}
```
"""

    # Build messages with history
    messages = []
    for h in history[-WA_MAX_HISTORY:]:
        messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': message})

    # Tool use loop (team only — property_owner and tenants are read-only)
    use_tools = (role == 'team')
    actions_taken = []

    for _ in range(5):
        result = call_claude(messages, system_prompt, use_tools=use_tools)
        if 'error' in result:
            return jsonify({'reply': '⚠️ ' + result['error'], 'role': role})

        content = result.get('content', [])
        tool_uses = [c for c in content if c.get('type') == 'tool_use']
        text_blocks = [c for c in content if c.get('type') == 'text']

        if not tool_uses:
            reply_text = '\n'.join(b.get('text', '') for b in text_blocks).strip()
            # Save conversation + bump activity
            history.append({'role': 'user', 'content': message})
            history.append({'role': 'assistant', 'content': reply_text})
            WA_SESSIONS[norm_phone]['history'] = history[-WA_MAX_HISTORY:]
            WA_SESSIONS[norm_phone]['last_activity'] = _time.time()
            return jsonify({
                'reply': reply_text or '(no response)',
                'role': role,
                'actions': actions_taken,
            })

        # Execute tools
        messages.append({'role': 'assistant', 'content': content})
        tool_results = []
        for tu in tool_uses:
            tool_name = tu['name']
            tool_input = tu.get('input', {})
            tr = execute_tool(tool_name, tool_input)
            actions_taken.append({'tool': tool_name, 'input': tool_input, 'result': tr})
            tool_results.append({
                'type': 'tool_result',
                'tool_use_id': tu['id'],
                'content': _json.dumps(tr, ensure_ascii=False),
            })
        messages.append({'role': 'user', 'content': tool_results})

    return jsonify({'reply': 'Reached max iterations', 'role': role, 'actions': actions_taken})


@bp.route('/api/whatsapp-reset', methods=['POST'])
def whatsapp_reset():
    """Clear conversation history for a phone number."""
    data = request.json or {}
    phone = data.get('phone', '')
    if phone:
        WA_SESSIONS.pop(normalize_phone(phone), None)
    return jsonify({'ok': True})


# ── Team member CRUD ──
@bp.route('/api/team-members', methods=['GET'])
def list_team():
    return jsonify(query_db('SELECT * FROM team_members ORDER BY name'))


@bp.route('/api/team-members', methods=['POST'])
def create_team_member():
    from src.models import insert_db
    data = request.json
    tid = insert_db(
        'INSERT INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)',
        (data['name'], data['phone'], data.get('role', 'manager'),
         data.get('language', 'ru'), data.get('access_level', 'full'))
    )
    return jsonify({'id': tid}), 201
