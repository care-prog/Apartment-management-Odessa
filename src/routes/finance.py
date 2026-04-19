from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('finance', __name__)

# ── Office Expenses ──
@bp.route('/api/expenses', methods=['GET'])
def list_expenses():
    return jsonify(query_db('SELECT * FROM office_expenses ORDER BY date DESC'))

@bp.route('/api/expenses', methods=['POST'])
def create_expense():
    data = request.json
    eid = insert_db(
        'INSERT INTO office_expenses (description, amount, category, date, receipt_url, notes) VALUES (?, ?, ?, ?, ?, ?)',
        (data['description'], data['amount'], data.get('category', 'general'),
         data.get('date'), data.get('receipt_url'), data.get('notes')))
    return jsonify({'id': eid}), 201

@bp.route('/api/expenses/<int:eid>', methods=['PUT'])
def update_expense(eid):
    data = request.json
    execute_db('UPDATE office_expenses SET description=?, amount=?, category=?, date=?, notes=? WHERE id=?',
        (data.get('description'), data.get('amount'), data.get('category'), data.get('date'), data.get('notes'), eid))
    return jsonify({'ok': True})

@bp.route('/api/expenses/<int:eid>', methods=['DELETE'])
def delete_expense(eid):
    execute_db('DELETE FROM office_expenses WHERE id = ?', (eid,))
    return jsonify({'ok': True})

# ── Owner Payments ──
@bp.route('/api/owner-payments', methods=['GET'])
def list_owner_payments():
    owner_id = request.args.get('owner_id')
    query = '''SELECT op.*, o.name as owner_name FROM owner_payments op
               JOIN owners o ON op.owner_id = o.id'''
    args = []
    if owner_id:
        query += ' WHERE op.owner_id = ?'
        args.append(owner_id)
    query += ' ORDER BY op.payment_date DESC'
    return jsonify(query_db(query, args))

@bp.route('/api/owner-payments', methods=['POST'])
def create_owner_payment():
    data = request.json
    pid = insert_db(
        'INSERT INTO owner_payments (owner_id, amount, payment_date, method, period, notes) VALUES (?, ?, ?, ?, ?, ?)',
        (data['owner_id'], data['amount'], data['payment_date'],
         data.get('method', 'cash'), data.get('period'), data.get('notes')))
    return jsonify({'id': pid}), 201

# ── Time-series cash flow for charts ──
@bp.route('/api/cash-flow', methods=['GET'])
def cash_flow():
    """Returns last 12 months of income (rent) and expenses for charting."""
    # Income per month from rent payments
    income = query_db('''
        SELECT strftime('%Y-%m', payment_date) as period, COALESCE(SUM(amount), 0) as total
        FROM payments WHERE type = 'rent' AND status = 'paid' AND payment_date IS NOT NULL
        GROUP BY period ORDER BY period
    ''')
    expenses = query_db('''
        SELECT strftime('%Y-%m', date) as period, COALESCE(SUM(amount), 0) as total, category
        FROM office_expenses WHERE date IS NOT NULL
        GROUP BY period, category ORDER BY period
    ''')
    owner_payments = query_db('''
        SELECT strftime('%Y-%m', payment_date) as period, COALESCE(SUM(amount), 0) as total
        FROM owner_payments WHERE payment_date IS NOT NULL
        GROUP BY period ORDER BY period
    ''')

    # Build last-12-months series
    from datetime import datetime, timedelta
    today = datetime.now().replace(day=1)
    months = []
    for i in range(11, -1, -1):
        month = (today - timedelta(days=i*30)).replace(day=1)
        months.append(month.strftime('%Y-%m'))

    def series_for(rows, key='period'):
        d = {r[key]: r['total'] for r in rows}
        return [round(d.get(m, 0), 2) for m in months]

    # Aggregate expenses by month
    exp_by_month = {}
    for r in expenses:
        exp_by_month[r['period']] = exp_by_month.get(r['period'], 0) + r['total']
    expenses_series = [round(exp_by_month.get(m, 0), 2) for m in months]

    # Estimated income from active leases (when no real payments logged yet)
    total_rent = query_db("SELECT COALESCE(SUM(rent_amount), 0) as s FROM leases WHERE status = 'active'", one=True)['s']
    fee_pct = 0.10
    return jsonify({
        'months': months,
        'income': series_for(income),
        'expenses': expenses_series,
        'owner_payments': series_for(owner_payments),
        'estimated_monthly_income': total_rent,
        'estimated_monthly_fee': round(total_rent * fee_pct, 2),
    })


# ── Office Cash Summary ──
@bp.route('/api/office-cash', methods=['GET'])
def office_cash():
    total_rent = query_db("SELECT COALESCE(SUM(rent_amount), 0) as s FROM leases WHERE status = 'active'", one=True)['s']
    fee_pct = 0.10
    monthly_fee = round(total_rent * fee_pct)
    total_expenses = query_db("SELECT COALESCE(SUM(amount), 0) as s FROM office_expenses", one=True)['s']
    total_paid_owners = query_db("SELECT COALESCE(SUM(amount), 0) as s FROM owner_payments", one=True)['s']

    expenses_by_cat = query_db('''
        SELECT category, SUM(amount) as total, COUNT(*) as count
        FROM office_expenses GROUP BY category ORDER BY total DESC
    ''')

    recent_expenses = query_db('SELECT * FROM office_expenses ORDER BY date DESC LIMIT 20')

    return jsonify({
        'total_monthly_rent': total_rent,
        'fee_percentage': fee_pct,
        'monthly_fee': monthly_fee,
        'total_expenses': total_expenses,
        'total_paid_to_owners': total_paid_owners,
        'balance': monthly_fee - total_expenses,
        'expenses_by_category': expenses_by_cat,
        'recent_expenses': recent_expenses,
    })

# ── Property Detail (with owner financials) ──
@bp.route('/api/properties/<int:pid>/detail', methods=['GET'])
def property_detail(pid):
    prop = query_db('SELECT p.*, o.name as owner_name, o.id as oid FROM properties p LEFT JOIN owners o ON p.owner_id = o.id WHERE p.id = ?', (pid,), one=True)
    if not prop:
        return jsonify({'error': 'Not found'}), 404

    apartments = query_db('SELECT * FROM apartments WHERE property_id = ? ORDER BY number', (pid,))
    leases = query_db('''
        SELECT l.*, t.name as tenant_name, a.number as apt_number
        FROM leases l JOIN tenants t ON l.tenant_id = t.id JOIN apartments a ON l.apartment_id = a.id
        WHERE a.property_id = ? AND l.status = 'active' ORDER BY a.number
    ''', (pid,))
    maintenance = query_db('''
        SELECT mo.*, a.number as apt_number FROM maintenance_orders mo
        JOIN apartments a ON mo.apartment_id = a.id WHERE a.property_id = ? ORDER BY mo.created_at DESC
    ''', (pid,))
    documents = query_db('SELECT * FROM documents WHERE property_id = ? ORDER BY uploaded_at DESC', (pid,))

    total_rent = sum(l['rent_amount'] for l in leases)
    fee = round(total_rent * 0.10)

    owner_payments = []
    if prop.get('oid'):
        owner_payments = query_db('SELECT * FROM owner_payments WHERE owner_id = ? ORDER BY payment_date DESC', (prop['oid'],))

    total_paid = sum(op['amount'] for op in owner_payments)
    total_maintenance_cost = sum(m.get('cost') or 0 for m in maintenance)

    return jsonify({
        'property': prop,
        'apartments': apartments,
        'leases': leases,
        'maintenance': maintenance,
        'documents': documents,
        'owner_payments': owner_payments,
        'financials': {
            'monthly_rent': total_rent,
            'management_fee': fee,
            'owner_receives': total_rent - fee,
            'total_paid_to_owner': total_paid,
            'total_maintenance_cost': total_maintenance_cost,
        }
    })
