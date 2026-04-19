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
    """Returns ('team'|'tenant'|'unknown', user_data)."""
    p = normalize_phone(phone)
    if not p:
        return ('unknown', None)

    # Try team members first
    team = query_db("SELECT * FROM team_members WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') = ?", (p,), one=True)
    if team:
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

# Trigger keywords - user must send one to START a session
APT_TRIGGERS = ['apt', 'דירה', 'דיר', 'квартир', 'квартира', 'apartment', 'בוט', 'bot']


def _is_apt_trigger(text):
    if not text:
        return False
    lower = text.lower().strip()
    # Direct trigger word at start or alone
    for trig in APT_TRIGGERS:
        if lower == trig or lower.startswith(trig + ' ') or lower.startswith(trig + '?') or lower.startswith(trig + ',') or lower.startswith(trig + '.'):
            return True
    return False


# ── Meta WhatsApp Cloud API ──────────────────────────────────────────────────

WA_PHONE_ID   = os.environ.get('WHATSAPP_PHONE_ID', '')
WA_TOKEN      = os.environ.get('WHATSAPP_TOKEN', '')
WA_VERIFY_TOK = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'odessa-whatsapp-2026')
WA_API_URL    = 'https://graph.facebook.com/v19.0'


def wa_send(to_phone, text):
    """Send a WhatsApp text message via Meta Cloud API."""
    if not WA_PHONE_ID or not WA_TOKEN:
        return {'error': 'WhatsApp credentials not set'}
    url = f'{WA_API_URL}/{WA_PHONE_ID}/messages'
    payload = {
        'messaging_product': 'whatsapp',
        'to': to_phone,
        'type': 'text',
        'text': {'body': text[:4096]},
    }
    resp = _requests.post(url, json=payload,
                          headers={'Authorization': f'Bearer {WA_TOKEN}',
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

        # ── Route through existing logic ──────────────────────────────────
        from src.routes.chat import call_claude, gather_context, execute_tool, TOOLS, LANG_NAMES
        import json as _json
        import time as _time

        role, user = identify_sender(from_phone)

        norm_phone = normalize_phone(from_phone) or from_phone
        now = _time.time()
        session = WA_SESSIONS.get(norm_phone)
        has_active = session and (now - session.get('last_activity', 0)) < SESSION_TIMEOUT_SECONDS
        if session and not has_active:
            del WA_SESSIONS[norm_phone]

        is_trigger = _is_apt_trigger(message_body)

        # Start session on trigger
        if is_trigger and not has_active:
            WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}
            if role == 'team':
                reply = f"שלום {user['name']}! 👋\nאיך אני יכול לעזור?\n• מידע על דירה\n• פתיחת משימה\n• עדכון סטטוס"
            elif role == 'tenant':
                reply = f"שלום {user.get('name','')}! 👋\nאיך אני יכול לעזור לך?"
            else:
                reply = "שלום! 👋\nאיזה דירה אתה שואל עליה ומה אתה צריך?"
            wa_send(from_phone, reply)
            return jsonify({'status': 'greeted'}), 200

        if not has_active and not is_trigger:
            # Silent ignore — don't reply to every message, only sessions
            return jsonify({'status': 'ignored'}), 200

        # Active session — full Claude response
        if norm_phone not in WA_SESSIONS:
            WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}
        WA_SESSIONS[norm_phone]['last_activity'] = now
        history = WA_SESSIONS[norm_phone]['history']

        user_lang  = user.get('language', 'he') if user else 'he'
        lang_name  = LANG_NAMES.get(user_lang, 'Hebrew')
        context    = gather_context()

        if role == 'team':
            access_note = (f"This user is a TEAM MEMBER ({user.get('name','')}, role: {user.get('role','')}). "
                           "Full access — answer any question, take any action.")
        elif role == 'tenant':
            apt_no = user.get('apt_number', '?')
            prop   = user.get('property_name', '')
            access_note = (f"This user is a TENANT ({user.get('name','')}) renting {prop} #{apt_no}. "
                           "Only share info about THEIR apartment. NO other tenant info, NO financials.")
        else:
            access_note = "UNKNOWN sender. Be polite, do NOT share any sensitive data. Ask who they are."

        system_prompt = f"""You are the WhatsApp assistant for "Apartment Management Odessa".
Be CONCISE — WhatsApp messages must be short. No markdown tables. Light emoji use only.
{access_note}
Respond in the same language the user wrote in (default: {lang_name}).

CURRENT DATA:
{_json.dumps(context, ensure_ascii=False, default=str)[:12000]}
"""
        messages_arr = []
        for h in history[-WA_MAX_HISTORY:]:
            messages_arr.append({'role': h['role'], 'content': h['content']})
        messages_arr.append({'role': 'user', 'content': message_body})

        use_tools   = (role == 'team')
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

    msg_lower = message.lower().strip()
    norm_phone = normalize_phone(phone) or phone  # fallback: use raw for mc_ IDs
    now = _time.time()

    # Check active session (hasn't timed out yet)
    session = WA_SESSIONS.get(norm_phone)
    has_active_session = (
        session is not None
        and (now - session.get('last_activity', 0)) < SESSION_TIMEOUT_SECONDS
    )

    # Garbage-collect expired session if present
    if session and not has_active_session:
        del WA_SESSIONS[norm_phone]

    is_trigger = _is_apt_trigger(message)

    # If it's a trigger word — start new session and greet
    if is_trigger and not has_active_session:
        WA_SESSIONS[norm_phone] = {'history': [], 'last_activity': now}
        if role == 'team':
            greeting = f"שלום {user['name']}! 👋\nאני העוזר של מערכת ניהול הדירות.\nאיך אני יכול לעזור?\n\nאתה יכול לבקש ממני:\n• מידע על דירה (לדוגמה: \"מה דירה 134\")\n• לפתוח משימה (לדוגמה: \"תפתח משימה לאלינה לבדוק בוילר בדירה 138\")\n• לעדכן סטטוס\n• כל שאלה אחרת"
        elif role == 'tenant':
            name = user.get('name', '')
            greeting = f"שלום {name}! 👋\nאיך אני יכול לעזור לך?"
        else:
            greeting = "שלום! 👋\nכדי שאוכל לעזור — תגיד לי על איזה דירה אתה שואל ומה אתה צריך."
        return jsonify({'reply': greeting, 'role': role})

    # If no active session AND no trigger — return a single zero-width space so ManyChat
    # can still render a "message" without showing anything to the user.
    # We also include silent:true in case you want to handle it differently later.
    if not has_active_session and not is_trigger:
        return jsonify({'reply': '\u200b', 'role': 'ignored', 'silent': True})

    # We have an active session — route through smart chat with Claude + tools
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

    # Different system prompt per role
    if role == 'team':
        access_note = "This user is a TEAM MEMBER ({}, role: {}). They have FULL access — answer any question, take any action.".format(
            user.get('name', ''), user.get('role', ''))
    elif role == 'tenant':
        apt_no = user.get('apt_number', 'unknown')
        prop = user.get('property_name', '')
        access_note = (f"This user is a TENANT named {user.get('name','')} renting {prop} #{apt_no}. "
                       "ONLY share information about THEIR apartment and lease (rent amount, due date, lease end, wifi, access codes if asked). "
                       "DO NOT share other tenants' info, owner financials, office cash, or other apartments. "
                       "DO NOT use tools that modify data — they can only ask questions. "
                       "If they ask for something you can't share, politely redirect them to contact the manager.")
    else:
        access_note = "This user is UNKNOWN (not in the system). Be polite but DO NOT share any sensitive info. Ask who they are and which apartment they're calling about."

    system_prompt = f"""You are the WhatsApp assistant for "Apartment Management Odessa".
You are talking via WhatsApp to one user. Be CONCISE — WhatsApp messages should be short and clear.
Use line breaks, bullets, emojis sparingly. NO markdown headers or tables (WhatsApp doesn't render them well).

{access_note}

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

    # Tool use loop (team only — tenants can't trigger actions)
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
        WA_CONVERSATIONS.pop(normalize_phone(phone), None)
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
