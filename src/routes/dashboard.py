from datetime import date
from flask import Blueprint, jsonify
from src.models import query_db

bp = Blueprint('dashboard', __name__)

@bp.route('/api/dashboard', methods=['GET'])
def dashboard_stats():
    total_units = query_db('SELECT COUNT(*) as c FROM apartments', one=True)['c']
    occupied = query_db("SELECT COUNT(*) as c FROM apartments WHERE status = 'occupied'", one=True)['c']
    vacant = query_db("SELECT COUNT(*) as c FROM apartments WHERE status = 'vacant'", one=True)['c']
    maintenance_count = query_db("SELECT COUNT(*) as c FROM apartments WHERE status = 'maintenance'", one=True)['c']

    today = date.today()
    month_start = today.replace(day=1).isoformat()
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1).isoformat()
    else:
        month_end = date(today.year, today.month + 1, 1).isoformat()

    overdue_rent = query_db('''
        SELECT COUNT(DISTINCT l.id) as c FROM leases l
        WHERE l.status = 'active'
        AND l.id NOT IN (
            SELECT lease_id FROM payments
            WHERE type = 'rent' AND status = 'paid'
            AND payment_date >= ? AND payment_date < ?
        )
    ''', (month_start, month_end), one=True)['c']

    total_rent = query_db("SELECT COALESCE(SUM(rent_amount), 0) as s FROM leases WHERE status = 'active'", one=True)['s']

    pending_tasks = query_db("SELECT COUNT(*) as c FROM tasks WHERE status = 'pending'", one=True)['c']
    in_progress_tasks = query_db("SELECT COUNT(*) as c FROM tasks WHERE status = 'in_progress'", one=True)['c']

    active_maintenance = query_db("SELECT COUNT(*) as c FROM maintenance_orders WHERE status != 'completed'", one=True)['c']

    properties = query_db('''
        SELECT p.*, o.name as owner_name,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id) as total_units,
            (SELECT COUNT(*) FROM apartments WHERE property_id = p.id AND status = 'occupied') as occupied_units,
            (SELECT COALESCE(SUM(l.rent_amount), 0) FROM leases l JOIN apartments a ON l.apartment_id = a.id WHERE a.property_id = p.id AND l.status = 'active') as monthly_rent
        FROM properties p LEFT JOIN owners o ON p.owner_id = o.id ORDER BY p.name
    ''')

    recent_tasks = query_db("""SELECT * FROM tasks
        ORDER BY
          CASE status WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'done' THEN 2 ELSE 3 END,
          CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
          due_date""")

    active_orders = query_db('''
        SELECT mo.*, a.number as apt_number, p.name as property_name
        FROM maintenance_orders mo
        JOIN apartments a ON mo.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE mo.status != 'completed'
        ORDER BY mo.created_at DESC LIMIT 10
    ''')

    upcoming_leases = query_db('''
        SELECT l.*, t.name as tenant_name, a.number as apt_number, p.name as property_name
        FROM leases l
        JOIN tenants t ON l.tenant_id = t.id
        JOIN apartments a ON l.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE l.status = 'active' AND l.end_date IS NOT NULL
        ORDER BY l.end_date LIMIT 5
    ''')

    rent_status = query_db('''
        SELECT l.id as lease_id, t.name as tenant_name, a.number as apt_number,
               p.name as property_name, l.rent_amount, l.start_date, l.end_date,
               a.notes as apt_notes,
               (SELECT MAX(payment_date) FROM payments WHERE lease_id = l.id AND type = 'rent' AND status = 'paid') as last_paid
        FROM leases l
        JOIN tenants t ON l.tenant_id = t.id
        JOIN apartments a ON l.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE l.status = 'active'
        ORDER BY p.name, a.number
    ''')

    from datetime import date as _date
    today = _date.today()
    for row in rent_status:
        end = row.get('end_date') or ''
        days = None
        if isinstance(end, str) and len(end) >= 10 and end[4:5] == '-' and end[7:8] == '-':
            try:
                days = (_date.fromisoformat(end[:10]) - today).days
            except Exception:
                days = None
        row['days_until_end'] = days

    owners = query_db('''
        SELECT o.*,
            (SELECT COALESCE(SUM(l.rent_amount), 0) FROM leases l JOIN apartments a ON l.apartment_id = a.id JOIN properties p ON a.property_id = p.id WHERE p.owner_id = o.id AND l.status = 'active') as monthly_income
        FROM owners o ORDER BY o.name
    ''')

    return jsonify({
        'stats': {
            'total_units': total_units,
            'occupied': occupied,
            'vacant': vacant,
            'maintenance': maintenance_count,
            'overdue_rent': overdue_rent,
            'total_monthly_rent': total_rent,
            'pending_tasks': pending_tasks,
            'in_progress_tasks': in_progress_tasks,
            'active_maintenance': active_maintenance,
        },
        'properties': properties,
        'tasks': recent_tasks,
        'maintenance': active_orders,
        'upcoming_leases': upcoming_leases,
        'rent_status': rent_status,
        'owners': owners,
    })
