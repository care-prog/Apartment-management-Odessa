"""
Voiceflow Webhook — provides a voice-friendly API endpoint for Voiceflow agents.
Voiceflow calls POST /api/voiceflow/ask with a question, we respond with an answer
built from live apartment data + Claude AI.

Embed in Voiceflow:
  URL: https://apartment-mgmt-odessa.onrender.com/api/voiceflow/ask
  Method: POST
  Headers: Content-Type: application/json
  Body: {"question": "{last_utterance}", "lang": "he"}
  Map response: answer → variable to speak
"""
import os
import json
import urllib.request
from flask import Blueprint, request, jsonify
from src.models import query_db

bp = Blueprint('voiceflow', __name__)

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
MODEL = 'claude-haiku-4-5-20251001'


def _get_api_key():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'
        )
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith('ANTHROPIC_API_KEY='):
                    key = line.split('=', 1)[1].strip()
    return key


def _build_voice_context():
    """Pull essential data from DB for voice queries. Lightweight version of gather_context."""
    try:
        apartments = query_db("""
            SELECT a.id, a.number, a.status, a.monthly_rent,
                   p.name as property_name,
                   t.name as tenant_name, t.phone as tenant_phone,
                   l.start_date, l.end_date, l.rent_amount
            FROM apartments a
            JOIN properties p ON a.property_id = p.id
            LEFT JOIN leases l ON l.apartment_id = a.id AND l.status = 'active'
            LEFT JOIN tenants t ON l.tenant_id = t.id
            ORDER BY p.name, a.number
        """)
        total = len(apartments)
        occupied = sum(1 for a in apartments if a['status'] == 'occupied')
        vacant = total - occupied
        total_rent = sum(
            float(a['rent_amount'] or a['monthly_rent'] or 0)
            for a in apartments if a['status'] == 'occupied'
        )

        tasks = query_db("""
            SELECT title, status, priority, due_date FROM tasks
            WHERE status != 'done' ORDER BY id DESC LIMIT 10
        """)
        maintenance = query_db("""
            SELECT mo.description, mo.status, a.number, p.name as property_name
            FROM maintenance_orders mo
            JOIN apartments a ON mo.apartment_id = a.id
            JOIN properties p ON a.property_id = p.id
            WHERE mo.status != 'completed'
            ORDER BY mo.created_at DESC LIMIT 10
        """)

        return {
            'summary': {
                'total_units': total,
                'occupied': occupied,
                'vacant': vacant,
                'occupancy_rate': f'{round(occupied / total * 100)}%' if total else '0%',
                'monthly_rent_total_usd': round(total_rent),
            },
            'apartments': [dict(a) for a in apartments],
            'open_tasks': [dict(t) for t in tasks],
            'open_maintenance': [dict(m) for m in maintenance],
        }
    except Exception as e:
        return {'error': str(e)}


SYSTEM_PROMPT = """You are a voice assistant for an apartment management company in Odessa, Ukraine.
You answer questions about apartments, tenants, rent payments, maintenance, and tasks.

Rules for voice responses:
- Keep answers SHORT and SPOKEN — 1-4 sentences max
- No bullet points, no markdown, no lists — plain speech only
- Numbers: say them naturally ("fifteen hundred dollars", not "1,500")
- Dates: say naturally ("April twenty-fifth", not "2026-04-25")
- If asked in Hebrew → answer in Hebrew
- If asked in Russian → answer in Russian
- If asked in English → answer in English
- Be direct and factual — this is voice, not chat

You have real-time data from the apartment management system below."""


@bp.route('/api/voiceflow/ask', methods=['POST', 'GET'])
def voiceflow_ask():
    """
    Main webhook for Voiceflow agents.

    Expected body (POST):
      { "question": "...", "lang": "he" }

    Or GET params: ?question=...&lang=he

    Returns:
      { "answer": "...", "success": true }
    """
    if request.method == 'GET':
        question = request.args.get('question', '').strip()
        lang = request.args.get('lang', 'ru')
    else:
        d = request.json or {}
        question = (d.get('question') or d.get('text') or d.get('utterance') or '').strip()
        lang = d.get('lang') or d.get('language') or 'ru'

    if not question:
        return jsonify({'answer': 'I did not receive a question. Please try again.', 'success': False}), 400

    api_key = _get_api_key()
    if not api_key:
        return jsonify({'answer': 'AI service is not configured.', 'success': False}), 500

    context = _build_voice_context()
    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    user_message = f"Question (in language: {lang}): {question}\n\nCurrent system data:\n{context_json}"

    payload = {
        'model': MODEL,
        'max_tokens': 256,
        'system': SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': user_message}]
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            result = json.loads(resp.read())

        answer = result['content'][0]['text'].strip()
        return jsonify({'answer': answer, 'success': True})

    except Exception as e:
        fallback = f"Sorry, I could not retrieve that information right now. Error: {str(e)[:100]}"
        return jsonify({'answer': fallback, 'success': False}), 500


@bp.route('/api/voiceflow/status', methods=['GET'])
def voiceflow_status():
    """Health check for Voiceflow — confirms the webhook is reachable."""
    ctx = _build_voice_context()
    summary = ctx.get('summary', {})
    return jsonify({
        'status': 'ok',
        'webhook_url': 'https://apartment-mgmt-odessa.onrender.com/api/voiceflow/ask',
        'method': 'POST',
        'body_fields': {'question': 'string (required)', 'lang': 'he/ru/en (optional)'},
        'response_fields': {'answer': 'string to speak', 'success': 'boolean'},
        'live_summary': summary,
    })
