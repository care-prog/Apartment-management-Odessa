"""
WhatsApp Notification Engine
============================
Sends event-driven WhatsApp notifications to David and Katya.

Event types:
  task_created, task_updated, task_closed
  payment_received, rent_overdue, rent_due_today
  lease_created, lease_expiring, lease_renewed
  expense_added, income_added, owner_payment
  property_added, apartment_added
  activity_log

Recipients:
  OWNER_PHONE  — all events (David)
  MANAGER_PHONE — management events only (Katya)

Opt-out: stored in notification_prefs table.
  User sends "STOP" → opted out
  User sends "START" → opted back in
"""
import os
import json
import datetime as _dt
from src.models import query_db, insert_db, execute_db

# ── Recipient config ──────────────────────────────────────────────────────────
OWNER_PHONE   = os.environ.get('OWNER_PHONE',   '972543006771')   # David
MANAGER_PHONE = os.environ.get('MANAGER_PHONE', '380505094050')   # Katya

# Events Katya receives (management / office)
MANAGER_EVENTS = {
    'task_created', 'task_updated', 'task_closed',
    'rent_due_today', 'rent_overdue',
    'lease_created', 'lease_expiring',
    'expense_added', 'activity_log',
}

# Events only David receives (financial overview, all)
OWNER_ONLY_EVENTS = {
    'income_added', 'owner_payment', 'property_added', 'apartment_added',
}


# ── Opt-out helpers ───────────────────────────────────────────────────────────
def _ensure_prefs_table():
    try:
        execute_db('''CREATE TABLE IF NOT EXISTS notification_prefs (
            phone TEXT PRIMARY KEY,
            opted_out INTEGER DEFAULT 0,
            opted_out_types TEXT DEFAULT '[]',
            updated_at TEXT
        )''')
    except Exception:
        pass


def is_opted_out(phone, event_type=None):
    _ensure_prefs_table()
    row = query_db('SELECT * FROM notification_prefs WHERE phone = ?', (phone,), one=True)
    if not row:
        return False
    if row['opted_out']:
        return True
    if event_type:
        try:
            types = json.loads(row.get('opted_out_types') or '[]')
            return event_type in types
        except Exception:
            pass
    return False


def set_opt_out(phone, opt_out=True, event_type=None):
    """Opt a phone number in or out. event_type=None means all events."""
    _ensure_prefs_table()
    if event_type is None:
        execute_db(
            '''INSERT INTO notification_prefs (phone, opted_out, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(phone) DO UPDATE SET opted_out=excluded.opted_out, updated_at=excluded.updated_at''',
            (phone, 1 if opt_out else 0, _dt.datetime.utcnow().isoformat())
        )
    else:
        row = query_db('SELECT opted_out_types FROM notification_prefs WHERE phone = ?', (phone,), one=True)
        types = []
        if row:
            try:
                types = json.loads(row['opted_out_types'] or '[]')
            except Exception:
                pass
        if opt_out and event_type not in types:
            types.append(event_type)
        elif not opt_out and event_type in types:
            types.remove(event_type)
        execute_db(
            '''INSERT INTO notification_prefs (phone, opted_out_types, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(phone) DO UPDATE SET opted_out_types=excluded.opted_out_types, updated_at=excluded.updated_at''',
            (phone, json.dumps(types), _dt.datetime.utcnow().isoformat())
        )


# ── Core send ─────────────────────────────────────────────────────────────────
def _wa_send_notification(phone, message):
    """Send via WhatsApp and log it."""
    from src.routes.whatsapp import wa_send
    result = wa_send(phone, message)
    ok = 'error' not in result
    try:
        insert_db(
            'INSERT INTO whatsapp_log (direction, from_phone, to_phone, sender_name, sender_role, body, status) VALUES (?,?,?,?,?,?,?)',
            ('out', 'notification', phone, 'System', 'system', message[:1000], 'sent' if ok else 'error')
        )
    except Exception:
        pass
    return ok


def notify(event_type, message_owner, message_manager=None):
    """
    Send notification to appropriate recipients.
    message_manager: if None, uses message_owner for Katya too.
    """
    msg_mgr = message_manager or message_owner

    # Send to owner (David) — always, unless opted out
    if not is_opted_out(OWNER_PHONE, event_type):
        _wa_send_notification(OWNER_PHONE, message_owner)

    # Send to manager (Katya) — only for management events
    if event_type in MANAGER_EVENTS and MANAGER_PHONE and MANAGER_PHONE != OWNER_PHONE:
        if not is_opted_out(MANAGER_PHONE, event_type):
            _wa_send_notification(MANAGER_PHONE, msg_mgr)


# ── Event formatters ──────────────────────────────────────────────────────────

def notify_task_created(task_id, title, assigned_to, priority, due_date):
    priority_icon = {'urgent': '🚨', 'high': '🔴', 'normal': '🟡', 'low': '🟢'}.get(priority, '📋')
    msg = (
        f"{priority_icon} *משימה חדשה*\n"
        f"📋 {title}\n"
        f"👤 שויך ל: {assigned_to or 'לא שויך'}\n"
        f"📅 תאריך יעד: {due_date or 'ללא'}"
    )
    msg_mgr = (
        f"{priority_icon} *Новая задача*\n"
        f"📋 {title}\n"
        f"👤 Назначено: {assigned_to or 'не назначено'}\n"
        f"📅 Срок: {due_date or 'нет'}"
    )
    notify('task_created', msg, msg_mgr)


def notify_task_status_changed(task_id, title, old_status, new_status, assigned_to):
    status_icons = {'pending': '⏳', 'in_progress': '🔄', 'done': '✅', 'cancelled': '❌'}
    icon = status_icons.get(new_status, '📋')
    status_he = {'pending': 'ממתין', 'in_progress': 'בביצוע', 'done': 'הושלם', 'cancelled': 'בוטל'}
    status_ru = {'pending': 'ожидает', 'in_progress': 'в работе', 'done': 'выполнено', 'cancelled': 'отменено'}

    if new_status == old_status:
        return  # No change

    msg = (
        f"{icon} *עדכון משימה*\n"
        f"📋 {title}\n"
        f"סטטוס: {status_he.get(old_status, old_status)} → *{status_he.get(new_status, new_status)}*"
    )
    msg_mgr = (
        f"{icon} *Обновление задачи*\n"
        f"📋 {title}\n"
        f"Статус: {status_ru.get(old_status, old_status)} → *{status_ru.get(new_status, new_status)}*"
    )
    event = 'task_closed' if new_status == 'done' else 'task_updated'
    notify(event, msg, msg_mgr)


def notify_payment_received(tenant_name, apartment, amount, currency='$'):
    msg = (
        f"💰 *תשלום התקבל*\n"
        f"👤 {tenant_name} — דירה {apartment}\n"
        f"💵 {currency}{amount:,.0f}"
    )
    notify('payment_received', msg)


def notify_expense_added(description, amount, category, currency='$'):
    cat_icons = {'utilities': '💡', 'repairs': '🔧', 'salary': '👷', 'rent': '🏠', 'general': '📦'}
    icon = cat_icons.get(category, '💸')
    msg = (
        f"{icon} *הוצאה חדשה*\n"
        f"📝 {description}\n"
        f"💵 {currency}{amount:,.0f} | קטגוריה: {category}"
    )
    msg_mgr = (
        f"{icon} *Новый расход*\n"
        f"📝 {description}\n"
        f"💵 {currency}{amount:,.0f} | {category}"
    )
    notify('expense_added', msg, msg_mgr)


def notify_lease_created(tenant_name, apartment, rent, end_date):
    msg = (
        f"📄 *חוזה חדש נחתם*\n"
        f"👤 {tenant_name} — דירה {apartment}\n"
        f"💵 ${rent:,.0f}/חודש\n"
        f"📅 עד: {end_date}"
    )
    msg_mgr = (
        f"📄 *Новый договор*\n"
        f"👤 {tenant_name} — кв. {apartment}\n"
        f"💵 ${rent:,.0f}/мес\n"
        f"📅 До: {end_date}"
    )
    notify('lease_created', msg, msg_mgr)


def notify_lease_expiring(tenant_name, apartment, end_date, days_left):
    urgency = '🚨' if days_left <= 7 else '⚠️'
    msg = (
        f"{urgency} *חוזה פג בקרוב*\n"
        f"👤 {tenant_name} — דירה {apartment}\n"
        f"📅 פג ב: {end_date} ({days_left} ימים)"
    )
    msg_mgr = (
        f"{urgency} *Договор истекает*\n"
        f"👤 {tenant_name} — кв. {apartment}\n"
        f"📅 Истекает: {end_date} (через {days_left} дн.)"
    )
    notify('lease_expiring', msg, msg_mgr)


def notify_rent_due_today(tenant_name, apartment, amount):
    msg = (
        f"📅 *שכירות לגביה היום*\n"
        f"👤 {tenant_name} — דירה {apartment}\n"
        f"💵 ${amount:,.0f}"
    )
    msg_mgr = (
        f"📅 *Аренда к сбору сегодня*\n"
        f"👤 {tenant_name} — кв. {apartment}\n"
        f"💵 ${amount:,.0f}"
    )
    notify('rent_due_today', msg, msg_mgr)


def notify_property_added(name, address):
    msg = f"🏢 *נכס חדש נוסף*\n📍 {name}\n🗺 {address or 'ללא כתובת'}"
    notify('property_added', msg)


def notify_owner_payment(owner_name, amount, period):
    msg = (
        f"💳 *תשלום לבעלים*\n"
        f"👤 {owner_name}\n"
        f"💵 ${amount:,.0f} | תקופה: {period or '-'}"
    )
    notify('owner_payment', msg)


# ── Scheduled checks (called by APScheduler daily) ───────────────────────────

def run_daily_checks():
    """
    Run daily at 9:00 Odessa time:
    1. Rent due today
    2. Leases expiring in 30, 14, 7, 3, 1 days
    Called from src/app.py scheduler.
    """
    today = _dt.date.today()
    today_str = today.isoformat()

    # ── Rent due today ───────────────────────────────────────────────────────
    try:
        # Leases where payment_day matches today's day-of-month and no payment this month
        day_of_month = today.day
        month_prefix = today.strftime('%Y-%m')
        due_leases = query_db('''
            SELECT l.id, l.rent_amount, t.name as tenant_name,
                   a.number as apt_number, p.name as property_name
            FROM leases l
            JOIN tenants t ON l.tenant_id = t.id
            JOIN apartments a ON l.apartment_id = a.id
            JOIN properties p ON a.property_id = p.id
            WHERE l.status = 'active'
        ''') or []

        for lease in due_leases:
            lease = dict(lease)
            # Check if payment already recorded this month
            paid = query_db(
                "SELECT id FROM payments WHERE lease_id = ? AND payment_date LIKE ? AND status = 'paid'",
                (lease['id'], f'{month_prefix}%'), one=True
            )
            if not paid:
                notify_rent_due_today(
                    lease['tenant_name'],
                    f"{lease['property_name']} #{lease['apt_number']}",
                    lease['rent_amount']
                )
    except Exception as e:
        print(f'[notifications] rent_due_today error: {e}')

    # ── Leases expiring ──────────────────────────────────────────────────────
    try:
        alert_days = [30, 14, 7, 3, 1]
        for days in alert_days:
            target = (today + _dt.timedelta(days=days)).isoformat()
            expiring = query_db('''
                SELECT l.end_date, l.rent_amount,
                       t.name as tenant_name,
                       a.number as apt_number, p.name as property_name
                FROM leases l
                JOIN tenants t ON l.tenant_id = t.id
                JOIN apartments a ON l.apartment_id = a.id
                JOIN properties p ON a.property_id = p.id
                WHERE l.status = 'active' AND l.end_date = ?
            ''', (target,)) or []
            for lease in expiring:
                lease = dict(lease)
                notify_lease_expiring(
                    lease['tenant_name'],
                    f"{lease['property_name']} #{lease['apt_number']}",
                    lease['end_date'],
                    days
                )
    except Exception as e:
        print(f'[notifications] lease_expiring error: {e}')
