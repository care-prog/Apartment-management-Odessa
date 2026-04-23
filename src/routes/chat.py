"""
Internal AI chat for the dashboard.
Uses Claude (Anthropic API) with Tool Use to answer questions AND
take actions (create tasks, add expenses, log payments, etc.).
"""
import os
import json
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('chat', __name__)

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
MODEL = 'claude-haiku-4-5-20251001'


def get_api_key():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith('ANTHROPIC_API_KEY='):
                    key = line.split('=', 1)[1].strip()
    return key


def gather_context():
    """Pull all relevant data from DB to give Claude full context."""
    properties = query_db("""
        SELECT p.id, p.name, p.address, p.notes, o.name as owner_name,
               (SELECT COUNT(*) FROM apartments WHERE property_id = p.id) as units,
               (SELECT COUNT(*) FROM apartments WHERE property_id = p.id AND status = 'occupied') as occupied
        FROM properties p LEFT JOIN owners o ON p.owner_id = o.id
        ORDER BY p.name
    """)

    apartments = query_db("""
        SELECT a.id as apt_id, a.number, a.status, a.monthly_rent, a.notes,
               p.name as property_name,
               t.id as tenant_id, t.name as tenant_name, t.phone as tenant_phone,
               l.id as lease_id, l.start_date, l.end_date, l.rent_amount
        FROM apartments a
        JOIN properties p ON a.property_id = p.id
        LEFT JOIN leases l ON l.apartment_id = a.id AND l.status = 'active'
        LEFT JOIN tenants t ON l.tenant_id = t.id
        ORDER BY p.name, a.number
    """)

    for a in apartments:
        try:
            extra = json.loads(a.get('notes') or '{}')
            a['payment_timeline'] = extra.get('timeline', '')
            a['meters'] = extra.get('meters', '')
            a.pop('notes', None)
        except:
            pass

    owners = query_db("SELECT id, name, contact, report_schedule, notes FROM owners ORDER BY name")
    tasks = query_db("SELECT id, title, assigned_to, status, due_date, priority FROM tasks ORDER BY id DESC LIMIT 20")
    maintenance = query_db("""
        SELECT mo.id, mo.description, mo.status, mo.assigned_to, mo.cost,
               a.number as apt_number, p.name as property_name
        FROM maintenance_orders mo
        JOIN apartments a ON mo.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE mo.status != 'completed'
        ORDER BY mo.created_at DESC LIMIT 30
    """)
    expenses = query_db("SELECT id, description, amount, category, date FROM office_expenses ORDER BY date DESC LIMIT 20")
    team = query_db("SELECT name, role, language FROM team_members ORDER BY name")

    # Professionals directory
    professionals = query_db("""
        SELECT p.id, p.name, p.phone, p.phone_2, p.messenger, p.category,
               p.notes, p.apartments_worked, p.rating,
               COALESCE(SUM(pp.amount), 0) AS total_paid
        FROM professionals p
        LEFT JOIN professional_payments pp ON pp.professional_id = p.id
        WHERE p.is_active = 1
        GROUP BY p.id
        ORDER BY p.category, p.name
    """)
    pro_list = []
    for p in professionals:
        pro_list.append({
            'id': p['id'],
            'name': p['name'],
            'phone': p['phone'] or '',
            'phone_2': p.get('phone_2') or '',
            'messenger': p.get('messenger') or 'Viber',
            'category': p['category'],
            'rating': p.get('rating') or 5,
            'total_paid': round(float(p['total_paid'] or 0), 2),
            'notes': p.get('notes') or '',
            'apartments_worked': p.get('apartments_worked') or '',
        })

    total_rent = query_db("SELECT COALESCE(SUM(rent_amount), 0) as s FROM leases WHERE status = 'active'", one=True)['s']
    fee = round(total_rent * 0.10)

    return {
        'summary': {
            'total_units': len(apartments),
            'occupied': sum(1 for a in apartments if a['status'] == 'occupied'),
            'vacant': sum(1 for a in apartments if a['status'] == 'vacant'),
            'monthly_rent_total_usd': total_rent,
            'management_fee_10pct_usd': fee,
        },
        'properties': properties,
        'apartments': apartments,
        'owners': owners,
        'team_members': team,
        'tasks': tasks,
        'open_maintenance': maintenance,
        'recent_expenses': expenses,
        'professionals': pro_list,
    }


# ── TOOL DEFINITIONS for Claude ──
TOOLS = [
    {
        'name': 'create_task',
        'description': 'Create a new task in the system. Use when the user asks to add/create a task, reminder, or to-do item.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string', 'description': 'Task title (short, clear)'},
                'assigned_to': {'type': 'string', 'description': 'Person assigned: David, Amalia, Alina, Anya, Katya, or other'},
                'due_date': {'type': 'string', 'description': 'Due date YYYY-MM-DD (optional)'},
                'priority': {'type': 'string', 'enum': ['low', 'normal', 'high', 'urgent'], 'description': 'Priority level'},
                'description': {'type': 'string', 'description': 'Optional longer description'},
                'notes': {'type': 'string', 'description': 'Short note or remark for this task'},
            },
            'required': ['title'],
        },
    },
    {
        'name': 'update_task',
        'description': (
            'Update an existing task — mark done/in_progress, change assignee, due date, priority, title, '
            'add/update notes or description. Can update ANY task regardless of status (including done/closed tasks). '
            'Use notes for comments, remarks, closing notes. Use description for longer context. '
            'Can also translate title/notes/description to any language — just pass the translated text.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'task_id': {'type': 'integer', 'description': 'ID of the task to update'},
                'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'done'], 'description': 'New status'},
                'assigned_to': {'type': 'string'},
                'due_date': {'type': 'string', 'description': 'YYYY-MM-DD'},
                'priority': {'type': 'string', 'enum': ['low', 'normal', 'high', 'urgent']},
                'title': {'type': 'string', 'description': 'Task title — can be updated or translated'},
                'notes': {'type': 'string', 'description': 'Short closing note / remark / comment about this task'},
                'description': {'type': 'string', 'description': 'Longer description or context for the task'},
            },
            'required': ['task_id'],
        },
    },
    {
        'name': 'add_expense',
        'description': 'Add an office expense (e.g. salary, utilities, supplies, repair costs)',
        'input_schema': {
            'type': 'object',
            'properties': {
                'description': {'type': 'string'},
                'amount': {'type': 'number', 'description': 'Amount in USD'},
                'category': {'type': 'string', 'description': 'e.g. salary, utilities, office, repair, marketing'},
                'date': {'type': 'string', 'description': 'YYYY-MM-DD, defaults to today'},
                'notes': {'type': 'string'},
            },
            'required': ['description', 'amount'],
        },
    },
    {
        'name': 'log_rent_payment',
        'description': 'Log a rent payment received from a tenant',
        'input_schema': {
            'type': 'object',
            'properties': {
                'lease_id': {'type': 'integer', 'description': 'ID of the lease'},
                'amount': {'type': 'number'},
                'payment_date': {'type': 'string', 'description': 'YYYY-MM-DD'},
                'method': {'type': 'string', 'enum': ['cash', 'transfer', 'card'], 'description': 'Payment method'},
                'notes': {'type': 'string'},
            },
            'required': ['lease_id', 'amount', 'payment_date'],
        },
    },
    {
        'name': 'log_owner_payment',
        'description': 'Log a payment made to a property owner',
        'input_schema': {
            'type': 'object',
            'properties': {
                'owner_id': {'type': 'integer'},
                'amount': {'type': 'number'},
                'payment_date': {'type': 'string'},
                'method': {'type': 'string', 'enum': ['cash', 'transfer', 'crypto'], 'default': 'cash'},
                'period': {'type': 'string', 'description': 'e.g. "March 2026"'},
                'notes': {'type': 'string'},
            },
            'required': ['owner_id', 'amount', 'payment_date'],
        },
    },
    {
        'name': 'create_maintenance_order',
        'description': 'Create a maintenance/repair order for an apartment',
        'input_schema': {
            'type': 'object',
            'properties': {
                'apartment_id': {'type': 'integer'},
                'description': {'type': 'string'},
                'assigned_to': {'type': 'string', 'description': 'e.g. Yura, Kirill'},
                'cost': {'type': 'number'},
            },
            'required': ['apartment_id', 'description'],
        },
    },
    {
        'name': 'update_apartment_status',
        'description': 'Change an apartment status (occupied/vacant/maintenance)',
        'input_schema': {
            'type': 'object',
            'properties': {
                'apartment_id': {'type': 'integer'},
                'status': {'type': 'string', 'enum': ['occupied', 'vacant', 'maintenance']},
            },
            'required': ['apartment_id', 'status'],
        },
    },
    {
        'name': 'log_professional_payment',
        'description': 'Log a payment made to a professional/contractor (plumber, cleaner, realtor, electrician, etc.). Use when the user says they paid someone from the professionals directory.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'professional_id': {'type': 'integer', 'description': 'ID of the professional from the professionals list'},
                'amount': {'type': 'number', 'description': 'Amount paid'},
                'currency': {'type': 'string', 'enum': ['USD', 'UAH'], 'description': 'Currency (default USD)'},
                'description': {'type': 'string', 'description': 'What the payment was for'},
                'payment_date': {'type': 'string', 'description': 'YYYY-MM-DD, defaults to today'},
            },
            'required': ['professional_id', 'amount'],
        },
    },
    {
        'name': 'find_professional',
        'description': 'Search the professionals directory by category or name. Use when the user asks "who do we use for X?" or "find me a plumber/cleaner/electrician/etc." Returns matching professionals with contact details.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'category': {'type': 'string', 'description': 'Category to filter by, e.g. Plumbing, Cleaning, Electrical, Realtor, Construction, etc.'},
                'name_search': {'type': 'string', 'description': 'Partial name search'},
            },
        },
    },
]


# ── TOOL EXECUTORS ──
def execute_tool(name, args):
    try:
        if name == 'create_task':
            tid = insert_db(
                'INSERT INTO tasks (title, description, assigned_to, due_date, status, priority, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (args['title'], args.get('description'), args.get('assigned_to'),
                 args.get('due_date'), 'pending', args.get('priority', 'normal'), args.get('notes'))
            )
            return {'success': True, 'task_id': tid, 'message': f'Task created: "{args["title"]}"'}

        if name == 'update_task':
            current = query_db('SELECT * FROM tasks WHERE id = ?', (args['task_id'],), one=True)
            if not current:
                return {'success': False, 'error': f'Task {args["task_id"]} not found'}
            execute_db(
                'UPDATE tasks SET title=?, assigned_to=?, due_date=?, status=?, priority=?, notes=?, description=? WHERE id=?',
                (args.get('title', current['title']),
                 args.get('assigned_to', current['assigned_to']),
                 args.get('due_date', current['due_date']),
                 args.get('status', current['status']),
                 args.get('priority', current['priority']),
                 args.get('notes', current['notes']),
                 args.get('description', current['description']),
                 args['task_id'])
            )
            changes = []
            if 'status' in args: changes.append(f"status → {args['status']}")
            if 'notes' in args: changes.append(f"note added")
            if 'title' in args: changes.append(f"title updated")
            return {'success': True, 'message': f'Task #{args["task_id"]} updated' + (': ' + ', '.join(changes) if changes else '')}

        if name == 'add_expense':
            from datetime import date
            eid = insert_db(
                'INSERT INTO office_expenses (description, amount, category, date, notes) VALUES (?, ?, ?, ?, ?)',
                (args['description'], args['amount'], args.get('category', 'general'),
                 args.get('date') or date.today().isoformat(), args.get('notes'))
            )
            return {'success': True, 'expense_id': eid, 'message': f'Expense logged: {args["description"]} (${args["amount"]})'}

        if name == 'log_rent_payment':
            pid = insert_db(
                'INSERT INTO payments (lease_id, type, amount, payment_date, method, status) VALUES (?, ?, ?, ?, ?, ?)',
                (args['lease_id'], 'rent', args['amount'], args['payment_date'],
                 args.get('method', 'cash'), 'paid')
            )
            return {'success': True, 'payment_id': pid, 'message': f'Rent payment logged: ${args["amount"]} on {args["payment_date"]}'}

        if name == 'log_owner_payment':
            pid = insert_db(
                'INSERT INTO owner_payments (owner_id, amount, payment_date, method, period, notes) VALUES (?, ?, ?, ?, ?, ?)',
                (args['owner_id'], args['amount'], args['payment_date'],
                 args.get('method', 'cash'), args.get('period'), args.get('notes'))
            )
            return {'success': True, 'payment_id': pid, 'message': f'Owner payment logged: ${args["amount"]}'}

        if name == 'create_maintenance_order':
            mid = insert_db(
                'INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to, cost) VALUES (?, ?, ?, ?, ?)',
                (args['apartment_id'], args['description'], 'reported',
                 args.get('assigned_to'), args.get('cost'))
            )
            return {'success': True, 'order_id': mid, 'message': f'Maintenance order created: {args["description"]}'}

        if name == 'update_apartment_status':
            execute_db('UPDATE apartments SET status = ? WHERE id = ?', (args['status'], args['apartment_id']))
            return {'success': True, 'message': f'Apartment #{args["apartment_id"]} → {args["status"]}'}

        if name == 'log_professional_payment':
            from datetime import date as _date
            pro = query_db('SELECT * FROM professionals WHERE id = ?', (args['professional_id'],), one=True)
            if not pro:
                return {'success': False, 'error': f'Professional #{args["professional_id"]} not found'}
            pay_id = insert_db(
                'INSERT INTO professional_payments (professional_id, amount, currency, description, payment_date) VALUES (?, ?, ?, ?, ?)',
                (args['professional_id'], float(args['amount']),
                 args.get('currency', 'USD'), args.get('description', ''),
                 args.get('payment_date') or _date.today().isoformat())
            )
            return {
                'success': True,
                'payment_id': pay_id,
                'message': f'Payment logged: {pro["name"]} — {args.get("currency","USD")} {args["amount"]} ({args.get("description","")})',
            }

        if name == 'find_professional':
            category = args.get('category', '').strip()
            name_search = args.get('name_search', '').strip()
            q = """
                SELECT p.id, p.name, p.phone, p.phone_2, p.messenger, p.category,
                       p.notes, p.rating, COALESCE(SUM(pp.amount),0) as total_paid
                FROM professionals p
                LEFT JOIN professional_payments pp ON pp.professional_id = p.id
                WHERE p.is_active = 1
            """
            qargs = []
            if category:
                q += ' AND p.category ILIKE ?' if False else ' AND LOWER(p.category) LIKE LOWER(?)'
                qargs.append(f'%{category}%')
            if name_search:
                q += ' AND LOWER(p.name) LIKE LOWER(?)'
                qargs.append(f'%{name_search}%')
            q += ' GROUP BY p.id ORDER BY p.rating DESC, p.name'
            rows = query_db(q, qargs)
            result = [dict(r) for r in rows]
            for r in result:
                r['total_paid'] = round(float(r['total_paid'] or 0), 2)
            return {'success': True, 'count': len(result), 'professionals': result}

        return {'success': False, 'error': f'Unknown tool: {name}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def call_claude(messages, system_prompt, use_tools=True):
    """Call Anthropic API with optional tool use."""
    key = get_api_key()
    if not key:
        return {'error': 'ANTHROPIC_API_KEY not configured'}

    payload = {
        'model': MODEL,
        'max_tokens': 2048,
        'system': system_prompt,
        'messages': messages,
    }
    if use_tools:
        payload['tools'] = TOOLS

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            'Content-Type': 'application/json',
            'x-api-key': key,
            'anthropic-version': '2023-06-01',
        }
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'error': f'API error {e.code}: {body[:300]}'}
    except Exception as e:
        return {'error': f'Request failed: {str(e)[:200]}'}


LANG_NAMES = {'he': 'Hebrew', 'en': 'English', 'ru': 'Russian'}

@bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    history = data.get('history', [])
    user_message = data.get('message', '')
    ui_lang = data.get('lang', 'en')
    user_tz = data.get('timezone', 'UTC')

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    # Compute current datetime in user's timezone
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = timezone.utc
    now_local = datetime.now(tz)
    current_date = now_local.strftime('%Y-%m-%d')
    current_datetime_str = now_local.strftime('%A, %d %B %Y, %H:%M') + f' ({user_tz})'

    context = gather_context()
    lang_name = LANG_NAMES.get(ui_lang, 'English')

    system_prompt = f"""You are an intelligent assistant for "Apartment Management Odessa" — a property management business in Odessa, Ukraine, owned by David Persiko.

TODAY: {current_datetime_str}  (use this as "today" for all tasks, deadlines, and date calculations — never guess the date)

You have FULL access to the live database AND can take actions using tools. The user (David) can ask you to:
- Read/answer questions about properties, tenants, finances, tasks, maintenance
- CREATE new tasks, expenses, payments, maintenance orders (use the appropriate tool)
- UPDATE existing items (mark task done, change apartment status, etc.)
- CONSULT about service providers / contractors — the professionals directory contains plumbers, cleaners, electricians, realtors, builders, etc. When the user asks "who do we use for X?" or "find me a Y" — use the find_professional tool to search by category or name, then return name + phone + rating + notes.
- LOG payments to professionals — when David says he paid a contractor, use log_professional_payment.

When the user asks you to do something (not just ask), USE THE APPROPRIATE TOOL. Don't just describe what should happen — actually do it.

LANGUAGE PREFERENCE:
- The user has set their dashboard interface to: {lang_name}.
- Default to responding in {lang_name} unless the user clearly writes in a different language.
- If the user writes in Hebrew → respond in Hebrew. If in Russian → respond in Russian. If in English → English. If in mix → match the dominant language.
- The user's language preference ({lang_name}) is the fallback when the input is ambiguous (numbers only, very short, etc.).

Be concise. After taking an action, briefly confirm what you did.

CURRENT DATABASE STATE:
```json
{json.dumps(context, ensure_ascii=False, default=str, indent=2)[:20000]}
```

Notes:
- "monthly_rent_total_usd" is total rent across active leases
- "management_fee_10pct_usd" is David's 10% fee
- Tenant placeholders: "Tenant Apt 134" means real name not yet entered
- For task assignment: use names from team_members (David, Amalia, Alina, Anya, Katya)
- professionals[] is the full service-provider directory. Categories include: Plumbing, Electrical, Cleaning, Realtor, Construction, Tile Work, Painting, Furniture, A/C, Locksmith, IT/Tech, Legal, Materials/Supply, Utilities, Internet/TV, Photography, Design, Neighbor Contact, Documents/Printing, Building Admin, Laundry, Windows/Glass, Fire Safety, Doors, Other
- Each professional has: id, name, phone, phone_2, messenger (WhatsApp/Viber/Telegram), category, rating (1-5), total_paid (historical), notes, apartments_worked
- Use find_professional tool for targeted searches rather than scanning the full list yourself
"""

    messages = []
    for h in history[-10:]:
        messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': user_message})

    # Multi-turn loop for tool use
    actions_taken = []
    for _ in range(5):  # Max 5 tool-use rounds
        result = call_claude(messages, system_prompt)

        if 'error' in result:
            return jsonify(result)

        # Check if Claude wants to use tools
        content = result.get('content', [])
        tool_uses = [c for c in content if c.get('type') == 'tool_use']
        text_blocks = [c for c in content if c.get('type') == 'text']

        if not tool_uses:
            # Final answer
            reply_text = '\n'.join(b.get('text', '') for b in text_blocks).strip()
            return jsonify({
                'reply': reply_text or '(no response)',
                'actions': actions_taken,
            })

        # Execute each tool and feed result back
        messages.append({'role': 'assistant', 'content': content})
        tool_results = []
        for tu in tool_uses:
            tool_name = tu['name']
            tool_input = tu.get('input', {})
            tool_result = execute_tool(tool_name, tool_input)
            actions_taken.append({'tool': tool_name, 'input': tool_input, 'result': tool_result})
            tool_results.append({
                'type': 'tool_result',
                'tool_use_id': tu['id'],
                'content': json.dumps(tool_result, ensure_ascii=False),
            })
        messages.append({'role': 'user', 'content': tool_results})

    return jsonify({'reply': 'Reached max tool-use iterations', 'actions': actions_taken})
