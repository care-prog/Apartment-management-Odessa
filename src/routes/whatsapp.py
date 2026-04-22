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


# ── Media helpers ─────────────────────────────────────────────────────────────

def wa_download_media(media_id):
    """Download a WhatsApp media file. Returns (bytes, mime_type) or (None, None)."""
    token = _get_wa_token()
    if not token:
        return None, None
    try:
        # Step 1: get the download URL
        info_resp = _requests.get(
            f'{WA_API_URL}/{media_id}',
            headers={'Authorization': f'Bearer {token}'}, timeout=15)
        info = info_resp.json()
        url = info.get('url')
        mime = info.get('mime_type', 'application/octet-stream')
        if not url:
            return None, None
        # Step 2: download the file
        file_resp = _requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'}, timeout=30)
        return file_resp.content, mime
    except Exception as e:
        print(f'[wa_download_media] error: {e}')
        return None, None


def analyze_image_with_claude(image_bytes, mime_type='image/jpeg', prompt=None):
    """Send image bytes to Claude Vision and return a description string."""
    try:
        import anthropic, base64
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return 'Image received but Claude API key not configured.'
        client = anthropic.Anthropic(api_key=api_key)
        img_b64 = base64.standard_b64encode(image_bytes).decode()
        # Clamp mime_type to what Claude accepts
        if mime_type not in ('image/jpeg', 'image/png', 'image/gif', 'image/webp'):
            mime_type = 'image/jpeg'
        text_prompt = (prompt or
            'Ты — помощник по управлению квартирами в Одессе. '
            'Опиши что видишь на фото. Если это квартира/комната — опиши состояние, '
            'любые повреждения или проблемы. Если это документ — кратко изложи его содержание. '
            'Будь конкретным и кратким (3-5 предложений).')
        resp = client.messages.create(
            model='claude-3-5-haiku-20241022',
            max_tokens=512,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image', 'source': {'type': 'base64',
                                                  'media_type': mime_type,
                                                  'data': img_b64}},
                    {'type': 'text', 'text': text_prompt},
                ]
            }]
        )
        return resp.content[0].text.strip() if resp.content else 'Не удалось проанализировать изображение.'
    except Exception as e:
        print(f'[analyze_image] error: {e}')
        return f'Не удалось проанализировать изображение: {str(e)[:80]}'


def transcribe_audio_with_whisper(audio_bytes, mime_type='audio/ogg'):
    """Transcribe audio bytes using OpenAI Whisper. Returns text or None."""
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        return None
    try:
        import openai, io
        client = openai.OpenAI(api_key=openai_key)
        # Determine file extension from mime_type
        ext_map = {
            'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp4': 'mp4',
            'audio/wav': 'wav', 'audio/webm': 'webm', 'audio/aac': 'aac',
        }
        ext = ext_map.get(mime_type, 'ogg')
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f'audio.{ext}'
        transcript = client.audio.transcriptions.create(
            model='whisper-1',
            file=audio_file,
            language=None,  # auto-detect language
        )
        return transcript.text.strip()
    except Exception as e:
        print(f'[whisper] error: {e}')
        return None


UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            'database', 'uploads')


def save_media_to_apartment(image_bytes, mime_type, apt_number, caption=''):
    """Save image file locally and record in documents table. Returns saved path or None."""
    try:
        import time as _time2
        from src.models import query_db as _qdb, insert_db as _idb
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        # Determine extension
        ext = 'jpg'
        if 'png' in mime_type: ext = 'png'
        elif 'webp' in mime_type: ext = 'webp'
        elif 'gif' in mime_type: ext = 'gif'
        filename = f'wa_{int(_time2.time())}_{apt_number}.{ext}'
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        # Find apartment
        apt = _qdb("SELECT * FROM apartments WHERE number = ?", (str(apt_number),), one=True)
        apt_id = apt['id'] if apt else None
        # Record in documents table
        _idb(
            "INSERT INTO documents (apartment_id, filename, category, notes, created_at)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (apt_id, filename, 'photo', caption or f'Фото из WhatsApp — кв. {apt_number}')
        )
        return filename
    except Exception as e:
        print(f'[save_media] error: {e}')
        return None


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
        print(f'[webhook] from={from_phone} type={msg_type} keys={list(msg.keys())}')

        # ── Media handling (image / audio / video) ───────────────────────
        from src.routes.chat import call_claude, gather_context, execute_tool, TOOLS, LANG_NAMES
        from src.models import insert_db as _ins
        import json as _json
        import time as _time

        role, user = identify_sender(from_phone)
        sender_name = (user or {}).get('name') or (user or {}).get('display_name') or from_phone
        message_body = ''  # Initialize here — set by text/voice blocks below

        if msg_type == 'image':
            media_id  = msg.get('image', {}).get('id', '')
            caption   = msg.get('image', {}).get('caption', '') or ''
            mime_type = msg.get('image', {}).get('mime_type', 'image/jpeg')
            print(f'[webhook] IMAGE media_id={media_id} mime={mime_type} caption={caption!r}')
            # Log as incoming image
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?)',
                     ('in', from_phone, sender_name, role, f'[IMAGE] {caption}'[:1000]))
            except Exception:
                pass
            # Download + analyze
            ack = '📸 מנתח את התמונה…' if role in ('team', 'property_owner') else '📸 Анализирую фото…'
            wa_send(from_phone, ack)
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?, ?)',
                     ('out', 'bot', from_phone, 'bot', 'bot', ack))
            except Exception:
                pass
            image_bytes, actual_mime = wa_download_media(media_id)
            print(f'[webhook] IMAGE download: got {len(image_bytes) if image_bytes else 0} bytes, mime={actual_mime}')
            if not image_bytes:
                err_msg = '❌ לא הצלחתי להוריד את התמונה. נסה שוב.' if role in ('team', 'property_owner') else '❌ Не удалось скачать фото. Попробуй ещё раз.'
                wa_send(from_phone, err_msg)
                try:
                    _ins('INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?, ?)',
                         ('out', 'bot', from_phone, 'bot', 'bot', err_msg))
                except Exception:
                    pass
                return jsonify({'status': 'media_download_failed'}), 200
            description = analyze_image_with_claude(image_bytes, actual_mime or mime_type)
            print(f'[webhook] IMAGE claude desc: {description[:100] if description else "NONE"}')
            # Store last image in session for follow-up save commands
            norm_phone_img = normalize_phone(from_phone) or from_phone
            if norm_phone_img not in WA_SESSIONS:
                WA_SESSIONS[norm_phone_img] = {'history': [], 'last_activity': _time.time()}
            WA_SESSIONS[norm_phone_img]['last_image'] = {
                'bytes': image_bytes, 'mime': actual_mime or mime_type,
                'caption': caption, 'media_id': media_id,
            }
            WA_SESSIONS[norm_phone_img]['last_activity'] = _time.time()
            reply = f'📸 *Фото:*\n{description}\n\n_Чтобы сохранить — напиши: "сохрани к квартире [номер]"_'
            wa_send(from_phone, reply)
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?, ?)',
                     ('out', 'bot', from_phone, 'bot', 'bot', reply[:1000]))
            except Exception:
                pass
            return jsonify({'status': 'image_analyzed'}), 200

        elif msg_type in ('audio', 'voice'):
            media_id  = msg.get(msg_type, {}).get('id', '')
            mime_type = msg.get(msg_type, {}).get('mime_type', 'audio/ogg')
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?)',
                     ('in', from_phone, sender_name, role, '[VOICE MESSAGE]'))
            except Exception:
                pass
            wa_send(from_phone, '🎙️ Transcribing…')
            audio_bytes, actual_mime = wa_download_media(media_id)
            if not audio_bytes:
                wa_send(from_phone, '❌ Could not download audio. Please send as text.')
                return jsonify({'status': 'media_download_failed'}), 200
            text = transcribe_audio_with_whisper(audio_bytes, actual_mime or mime_type)
            if not text:
                wa_send(from_phone, '⚠️ Voice transcription not available. Please send your message as text.')
                return jsonify({'status': 'no_whisper_key'}), 200
            # Re-enter webhook logic with transcribed text
            message_body = text
            msg_type = 'text'  # Fall through to text handling below
            log_prefix = f'[VOICE→TEXT] {text}'
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?)',
                     ('in', from_phone, sender_name, role, log_prefix[:1000]))
            except Exception:
                pass

        elif msg_type != 'text':
            # Unsupported type (video, sticker, document, etc.)
            wa_send(from_phone, '⚠️ I can process text, images, and voice messages. Please send one of those.')
            return jsonify({'status': 'unsupported_type'}), 200

        if msg_type == 'text' and not message_body:
            message_body = msg.get('text', {}).get('body', '').strip()
        if not message_body:
            return jsonify({'status': 'empty'}), 200

        # Log every incoming text message
        try:
            _ins('INSERT INTO whatsapp_log (direction, from_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?)',
                 ('in', from_phone, sender_name, role, message_body[:1000]))
        except Exception:
            pass

        # ── Check for "save to apartment X" command ───────────────────────
        norm_phone_check = normalize_phone(from_phone) or from_phone
        save_match = re.search(
            r'(?:сохрани|save|שמור).*?(?:кв(?:артир[уы]?)?\.?|дирк[уы]?|apartment|apt|#|דירה)\s*(\d+(?:/\d+)?)',
            message_body, re.IGNORECASE)
        if save_match:
            apt_no = save_match.group(1)
            last_img = (WA_SESSIONS.get(norm_phone_check) or {}).get('last_image')
            if last_img:
                saved = save_media_to_apartment(
                    last_img['bytes'], last_img['mime'], apt_no,
                    caption=last_img.get('caption') or f'Из WhatsApp от {sender_name}')
                if saved:
                    wa_send(from_phone, f'✅ Фото сохранено к квартире {apt_no} ({saved})')
                else:
                    wa_send(from_phone, f'❌ Не удалось сохранить фото к квартире {apt_no}')
                return jsonify({'status': 'image_saved'}), 200
            else:
                wa_send(from_phone, '⚠️ Нет недавнего фото для сохранения. Сначала отправь фото.')
                return jsonify({'status': 'no_recent_image'}), 200

        # ── Bot pause check (owner took over manually) ────────────────────
        from src.models import get_setting as _gs
        if _gs(f'wa_bot_paused_{from_phone}') == '1':
            # Message logged, but bot stays silent — owner handles it from dashboard
            return jsonify({'status': 'bot_paused'}), 200

        # ── Opt-out / Opt-in commands ─────────────────────────────────────────
        msg_upper = message_body.strip().upper()
        if msg_upper in ('STOP', 'עצור', 'СТОП'):
            from src.notifications import set_opt_out
            set_opt_out(from_phone, opt_out=True)
            wa_send(from_phone, '🔕 הסרת את עצמך מרשימת ההתראות.\nשלח START כדי לחזור.')
            return jsonify({'status': 'opted_out'}), 200
        if msg_upper in ('START', 'התחל', 'СТАРТ'):
            from src.notifications import set_opt_out
            set_opt_out(from_phone, opt_out=False)
            wa_send(from_phone, '🔔 נרשמת מחדש לקבלת התראות!')
            return jsonify({'status': 'opted_in'}), 200

        # Unknown number → reject immediately, no Claude call
        if role == 'unknown':
            rejection = ("אני לא מזהה אותך במערכת.\n"
                         "I don't recognize your number in the system.\n"
                         "Please contact the system administrator. 🔒")
            wa_send(from_phone, rejection)
            try:
                _ins('INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     ('out', 'bot', from_phone, 'bot', 'bot', rejection[:1000], 'rejected_unknown'))
            except Exception:
                pass
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
            user_role = user.get('role', '')
            user_lang = user.get('language', 'he')
            if user_lang == 'ru':
                access_note = (
                    f"This user is a TEAM MEMBER. Name: {display_name}, role: {user_role}. "
                    "Full access — answer any question, take any action. "
                    "IMPORTANT TONE: Always address her respectfully and warmly. She is a key manager. "
                    "Be polite, professional, and eager to help. Show that you take her requests seriously."
                )
            else:
                access_note = (f"This user is a TEAM MEMBER. Name: {display_name}, role: {user_role}. "
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

        user_lang_code = user.get('language', 'he') if user else 'he'
        if is_new_session:
            if user_lang_code == 'ru':
                greeting_instruction = (
                    f"IMPORTANT: This is the FIRST message in a new conversation. "
                    f"Start with a warm, respectful Russian greeting specifically for {display_name}. "
                    f"Say something like: 'Катя, понимаю, что ты тут главная 😊 — чем могу помочь? "
                    f"Сделаю всё возможное!' — then immediately answer their question in Russian."
                )
            else:
                greeting_instruction = (
                    f"IMPORTANT: This is the FIRST message from this person in a new conversation. "
                    f"Start your reply with a warm greeting: 'שלום {display_name}! 👋' "
                    f"then immediately answer their question."
                )
        else:
            greeting_instruction = ""

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
                # Log outgoing reply
                try:
                    _ins('INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body) VALUES (?, ?, ?, ?, ?, ?)',
                         ('out', 'bot', from_phone, 'bot', 'bot', (reply_text or '✓')[:1000]))
                except Exception:
                    pass
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
@bp.route('/api/whatsapp/log', methods=['GET'])
def wa_log():
    """Return WA log. Supports ?limit=50&offset=0&entity_type=professional&entity_id=5&phone=xxx"""
    limit  = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    entity_type = request.args.get('entity_type', '')
    entity_id   = request.args.get('entity_id', '')
    phone       = request.args.get('phone', '')

    where = 'WHERE 1=1'
    args = []
    if entity_type:
        where += ' AND entity_type = ?'
        args.append(entity_type)
    if entity_id:
        where += ' AND entity_id = ?'
        args.append(int(entity_id))
    if phone:
        where += ' AND (from_phone = ? OR to_phone = ?)'
        args.extend([phone, phone])

    total = (query_db(f'SELECT COUNT(*) as c FROM whatsapp_log {where}', args, one=True) or {}).get('c', 0)
    rows  = query_db(f'SELECT * FROM whatsapp_log {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
                     args + [limit, offset])
    return jsonify({'messages': [dict(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit})


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


@bp.route('/api/whatsapp/conversations', methods=['GET'])
def wa_conversations():
    """Return list of conversations grouped by external phone, sorted by latest activity."""
    from src.models import get_setting, query_db as _qdb
    rows = query_db(
        """SELECT direction, from_phone, to_phone, sender_name, sender_role, body, status, created_at
           FROM whatsapp_log
           WHERE (direction='in' AND from_phone IS NOT NULL AND from_phone != 'bot')
              OR (direction='out' AND to_phone IS NOT NULL AND to_phone != 'bot')
           ORDER BY created_at ASC"""
    )
    convos = {}
    for r in rows:
        r = dict(r)
        ext = r['from_phone'] if r['direction'] == 'in' else r['to_phone']
        if not ext or ext in ('bot', 'dashboard', 'cron'):
            continue
        if ext not in convos:
            convos[ext] = {
                'phone': ext,
                'contact_name': r.get('sender_name') or ext,
                'role': r.get('sender_role') or 'unknown',
                'last_message': r['body'] or '',
                'last_direction': r['direction'],
                'last_time': r['created_at'],
                'msg_count': 0,
                'unread': 0,
            }
        c = convos[ext]
        c['last_message'] = r['body'] or ''
        c['last_direction'] = r['direction']
        c['last_time'] = r['created_at']
        c['msg_count'] += 1
        if r['direction'] == 'in':
            # Update name/role from most recent inbound
            if r.get('sender_name') and r['sender_name'] != ext:
                c['contact_name'] = r['sender_name']
            if r.get('sender_role'):
                c['role'] = r['sender_role']

    # Enrich with opt-out + bot-pause status
    for phone, c in convos.items():
        try:
            pref = _qdb('SELECT opted_out FROM notification_prefs WHERE phone = ?', (phone,), one=True)
            c['opted_out'] = bool(pref and pref.get('opted_out'))
        except Exception:
            c['opted_out'] = False
        c['bot_paused'] = (get_setting(f'wa_bot_paused_{phone}') == '1')

    result = sorted(convos.values(), key=lambda x: x['last_time'] or '', reverse=True)
    return jsonify(result)


@bp.route('/api/whatsapp/conversations/<path:phone>', methods=['GET'])
def wa_conversation_thread(phone):
    """Return all messages for a specific phone number conversation."""
    rows = query_db(
        """SELECT id, direction, from_phone, to_phone, sender_name, sender_role,
                  body, status, created_at
           FROM whatsapp_log
           WHERE from_phone = ? OR to_phone = ?
           ORDER BY created_at ASC""",
        (phone, phone)
    )
    msgs = []
    for r in rows:
        r = dict(r)
        # Filter out bot↔bot rows
        if r.get('from_phone') == 'bot' and r.get('to_phone') == 'bot':
            continue
        msgs.append(r)
    return jsonify(msgs)


@bp.route('/api/whatsapp/conversations/<path:phone>/bot-pause', methods=['POST'])
def wa_bot_pause(phone):
    """Toggle bot-pause for a phone number. When paused, bot won't auto-reply."""
    from src.models import get_setting, set_setting
    d = request.json or {}
    paused = bool(d.get('paused', True))
    set_setting(f'wa_bot_paused_{phone}', '1' if paused else '0')
    return jsonify({'ok': True, 'phone': phone, 'bot_paused': paused})


@bp.route('/api/whatsapp/conversations/<path:phone>/opt-out', methods=['POST'])
def wa_opt_out_toggle(phone):
    """Owner can manually toggle opt-out for a contact from dashboard."""
    d = request.json or {}
    opted_out = bool(d.get('opted_out', True))
    from src.notifications import set_opt_out
    set_opt_out(phone, opt_out=opted_out)
    return jsonify({'ok': True, 'phone': phone, 'opted_out': opted_out})


@bp.route('/api/whatsapp/send', methods=['POST'])
def wa_dashboard_send():
    """Send a WhatsApp message from the dashboard."""
    from src.auth import get_current_role
    from src.models import insert_db
    d = request.json or {}
    to   = (d.get('to') or '').strip().lstrip('+')
    body = (d.get('message') or '').strip()
    if not to or not body:
        return jsonify({'error': 'to and message required'}), 400
    result = wa_send(to, body)
    if 'error' in result:
        return jsonify({'error': result['error']}), 400
    try:
        insert_db(
            'INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            ('out', 'dashboard', to, 'Dashboard', 'team', body[:1000], 'sent')
        )
    except Exception:
        pass
    return jsonify({'ok': True, 'message_id': result.get('messages', [{}])[0].get('id', '')})


@bp.route('/api/cron/hourly-report', methods=['GET', 'POST'])
def hourly_report():
    """
    Server-side hourly status report — sends WhatsApp update to owner.
    Called by an external cron (cron-job.org / Make.com) every hour.
    Protected by CRON_SECRET query param or X-Cron-Secret header.
    Public endpoint (no login required) so external cron can hit it.
    """
    import datetime as _dt
    from src.models import get_setting

    # ── Auth: simple secret ─────────────────────────────────────────────────
    expected_secret = os.environ.get('CRON_SECRET', 'odessa-cron-2026')
    provided = (request.args.get('secret') or
                request.headers.get('X-Cron-Secret') or
                (request.json or {}).get('secret', '') if request.is_json else '')
    if provided != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401

    # ── Gather status ───────────────────────────────────────────────────────
    now_utc = _dt.datetime.utcnow()
    now_str  = (now_utc + _dt.timedelta(hours=3)).strftime('%H:%M')  # Odessa time (UTC+3)

    # Token check
    try:
        token   = _get_wa_token()
        phone_id = _get_wa_phone_id()
        import requests as _req
        r = _req.get(
            f'https://graph.facebook.com/debug_token',
            params={'input_token': token, 'access_token': token},
            timeout=8
        )
        tdata    = r.json().get('data', {})
        tok_ok   = tdata.get('is_valid', False)
        tok_icon = '✅' if tok_ok else '❌'
        tok_text = 'תקין' if tok_ok else 'פג תוקף!'
    except Exception:
        tok_icon = '⚠️'
        tok_text = 'לא ניתן לבדוק'

    # Message counts
    try:
        all_msgs  = query_db('SELECT direction FROM whatsapp_log') or []
        today_str = now_utc.strftime('%Y-%m-%d')
        today_in  = query_db(
            "SELECT COUNT(*) as c FROM whatsapp_log WHERE direction='in' AND created_at >= ?",
            (today_str,), one=True
        )
        today_out = query_db(
            "SELECT COUNT(*) as c FROM whatsapp_log WHERE direction='out' AND created_at >= ?",
            (today_str,), one=True
        )
        count_in  = (today_in  or {}).get('c', 0)
        count_out = (today_out or {}).get('c', 0)
    except Exception:
        count_in = count_out = '?'

    # Pending items (hardcoded known list)
    pending = [
        'טוקן קבוע (System User) — ממתין לאישור אדמין שני',
        'ממשק תבניות WhatsApp',
        'שליחה המונית (broadcast)',
    ]

    # ── Build message ───────────────────────────────────────────────────────
    pending_lines = '\n'.join(f'  • {p}' for p in pending)
    message = (
        f"🕐 דוח שעתי — {now_str} (אודסה)\n"
        f"\n"
        f"📡 טוקן WA: {tok_icon} {tok_text}\n"
        f"💬 הודעות היום: {count_in} נכנסו / {count_out} יצאו\n"
        f"🌐 שרת: פעיל ✅\n"
        f"\n"
        f"📋 ממתין לביצוע:\n{pending_lines}"
    )

    # ── Send ────────────────────────────────────────────────────────────────
    owner_phone = os.environ.get('OWNER_PHONE', '972543006771')
    result = wa_send(owner_phone, message)
    ok     = 'error' not in result

    # Log it
    try:
        from src.models import insert_db as _ins
        _ins(
            'INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body, status) VALUES (?,?,?,?,?,?,?)',
            ('out', 'cron', owner_phone, 'Cron', 'system', message[:1000], 'sent' if ok else 'error')
        )
    except Exception:
        pass

    return jsonify({
        'ok': ok,
        'time': now_str,
        'token_valid': tok_ok if isinstance(tok_ok, bool) else None,
        'messages_today_in': count_in,
        'messages_today_out': count_out,
        'wa_result': result,
    })


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
