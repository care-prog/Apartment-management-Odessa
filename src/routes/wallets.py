"""Cash wallet management: USD and UAH transactions + commission per apartment."""
from flask import Blueprint, request, jsonify
from src.models import query_db, insert_db, execute_db

bp = Blueprint('wallets', __name__)


# ── Cash Transactions ──

@bp.route('/api/transactions', methods=['GET'])
def list_transactions():
    currency = request.args.get('currency')
    query = 'SELECT * FROM cash_transactions'
    args = []
    if currency:
        query += ' WHERE currency = ?'
        args.append(currency)
    query += ' ORDER BY transaction_date DESC, created_at DESC'
    return jsonify(query_db(query, args))


@bp.route('/api/transactions', methods=['POST'])
def create_transaction():
    data = request.json
    tid = insert_db(
        'INSERT INTO cash_transactions (type, amount, currency, category, description, transaction_date) VALUES (?, ?, ?, ?, ?, ?)',
        (data['type'], data['amount'], data.get('currency', 'USD'),
         data.get('category', 'general'), data.get('description'), data.get('transaction_date'))
    )
    return jsonify({'id': tid}), 201


@bp.route('/api/transactions/<int:tid>', methods=['PUT'])
def update_transaction(tid):
    data = request.json
    execute_db(
        'UPDATE cash_transactions SET type=?, amount=?, currency=?, category=?, description=?, transaction_date=? WHERE id=?',
        (data.get('type'), data.get('amount'), data.get('currency', 'USD'),
         data.get('category'), data.get('description'), data.get('transaction_date'), tid)
    )
    return jsonify({'ok': True})


@bp.route('/api/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    execute_db('DELETE FROM cash_transactions WHERE id = ?', (tid,))
    return jsonify({'ok': True})


@bp.route('/api/wallets', methods=['GET'])
def wallet_summary():
    """Returns current balance, income, and expenses for each currency."""
    result = {}
    for cur in ('USD', 'UAH'):
        income = query_db(
            "SELECT COALESCE(SUM(amount), 0) as s FROM cash_transactions WHERE type = 'income' AND currency = ?",
            (cur,), one=True)['s']
        expenses = query_db(
            "SELECT COALESCE(SUM(amount), 0) as s FROM cash_transactions WHERE type = 'expense' AND currency = ?",
            (cur,), one=True)['s']
        # Also include office_expenses with this currency
        office_exp = query_db(
            "SELECT COALESCE(SUM(amount), 0) as s FROM office_expenses WHERE currency = ?",
            (cur,), one=True)['s']
        total_out = round(expenses + office_exp, 2)
        result[cur] = {
            'currency': cur,
            'income': round(income, 2),
            'expenses': total_out,
            'balance': round(income - total_out, 2),
        }
    return jsonify(result)


# ── Commission Overrides ──

@bp.route('/api/commission/<monday_id>', methods=['GET'])
def get_commission(monday_id):
    row = query_db('SELECT * FROM commission_overrides WHERE monday_id = ?', (monday_id,), one=True)
    if not row:
        return jsonify({'monday_id': monday_id, 'commission_type': 'percent', 'commission_value': 10})
    return jsonify(row)


@bp.route('/api/commission/<monday_id>', methods=['PUT'])
def set_commission(monday_id):
    data = request.json
    existing = query_db('SELECT monday_id FROM commission_overrides WHERE monday_id = ?', (monday_id,), one=True)
    if existing:
        execute_db(
            'UPDATE commission_overrides SET commission_type=?, commission_value=?, notes=? WHERE monday_id=?',
            (data.get('commission_type', 'percent'), data.get('commission_value', 10),
             data.get('notes'), monday_id)
        )
    else:
        insert_db(
            'INSERT INTO commission_overrides (monday_id, commission_type, commission_value, notes) VALUES (?, ?, ?, ?)',
            (monday_id, data.get('commission_type', 'percent'),
             data.get('commission_value', 10), data.get('notes'))
        )
    return jsonify({'ok': True})


@bp.route('/api/commission', methods=['GET'])
def list_commissions():
    """Returns all commission overrides — used to overlay on apartment list."""
    rows = query_db('SELECT * FROM commission_overrides')
    return jsonify({r['monday_id']: r for r in rows})


# ── Financial Summary (date-range aware) ──

@bp.route('/api/cash-summary', methods=['GET'])
def cash_summary():
    """Date-range filtered summary: totals, monthly timeline, category breakdown.
    Query params: from=YYYY-MM-DD, to=YYYY-MM-DD, currency=USD|UAH
    """
    from src.models import month_str
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    currency = request.args.get('currency', 'USD')

    # Build parameterised WHERE snippets for each table
    txn_filter = ' AND currency = ?'
    txn_args = [currency]
    off_filter = ' AND currency = ?'
    off_args = [currency]

    if from_date:
        txn_filter += ' AND transaction_date >= ?'
        txn_args.append(from_date)
        off_filter += ' AND date >= ?'
        off_args.append(from_date)
    if to_date:
        txn_filter += ' AND transaction_date <= ?'
        txn_args.append(to_date)
        off_filter += ' AND date <= ?'
        off_args.append(to_date)

    # ── Totals ──
    total_inc = query_db(
        f"SELECT COALESCE(SUM(amount),0) as s FROM cash_transactions WHERE type='income'{txn_filter}",
        txn_args, one=True)['s']
    total_exp_txn = query_db(
        f"SELECT COALESCE(SUM(amount),0) as s FROM cash_transactions WHERE type='expense'{txn_filter}",
        txn_args, one=True)['s']
    total_off = query_db(
        f"SELECT COALESCE(SUM(amount),0) as s FROM office_expenses WHERE 1=1{off_filter}",
        off_args, one=True)['s']

    total_income = round(float(total_inc), 2)
    total_expenses = round(float(total_exp_txn) + float(total_off), 2)

    # ── Monthly timeline (cash_transactions) ──
    mf = month_str('transaction_date')
    monthly_rows = query_db(
        f"SELECT {mf} as month, type, COALESCE(SUM(amount),0) as total "
        f"FROM cash_transactions WHERE 1=1{txn_filter} GROUP BY month, type ORDER BY month",
        txn_args)
    months: dict = {}
    for r in monthly_rows:
        m = r['month'] or ''
        if not m:
            continue
        months.setdefault(m, {'month': m, 'income': 0.0, 'expenses': 0.0})
        if r['type'] == 'income':
            months[m]['income'] = round(float(r['total']), 2)
        else:
            months[m]['expenses'] = round(float(r['total']), 2)

    # Add office_expenses per month
    mf2 = month_str('date')
    off_monthly = query_db(
        f"SELECT {mf2} as month, COALESCE(SUM(amount),0) as total "
        f"FROM office_expenses WHERE 1=1{off_filter} GROUP BY month ORDER BY month",
        off_args)
    for r in off_monthly:
        m = r['month'] or ''
        if not m:
            continue
        months.setdefault(m, {'month': m, 'income': 0.0, 'expenses': 0.0})
        months[m]['expenses'] = round(months[m]['expenses'] + float(r['total']), 2)

    by_month = sorted(months.values(), key=lambda x: x['month'])
    for row in by_month:
        row['balance'] = round(row['income'] - row['expenses'], 2)

    # ── Category breakdown ──
    cats: dict = {}
    for r in query_db(
        f"SELECT category, COALESCE(SUM(amount),0) as total FROM cash_transactions "
        f"WHERE type='income'{txn_filter} GROUP BY category", txn_args):
        c = r['category'] or 'other'
        cats.setdefault(c, {'category': c, 'income': 0.0, 'expenses': 0.0})
        cats[c]['income'] = round(float(r['total']), 2)

    for r in query_db(
        f"SELECT category, COALESCE(SUM(amount),0) as total FROM cash_transactions "
        f"WHERE type='expense'{txn_filter} GROUP BY category", txn_args):
        c = r['category'] or 'other'
        cats.setdefault(c, {'category': c, 'income': 0.0, 'expenses': 0.0})
        cats[c]['expenses'] = round(cats[c].get('expenses', 0) + float(r['total']), 2)

    for r in query_db(
        f"SELECT category, COALESCE(SUM(amount),0) as total FROM office_expenses "
        f"WHERE 1=1{off_filter} GROUP BY category", off_args):
        c = r['category'] or 'general'
        cats.setdefault(c, {'category': c, 'income': 0.0, 'expenses': 0.0})
        cats[c]['expenses'] = round(cats[c].get('expenses', 0) + float(r['total']), 2)

    by_category = sorted(cats.values(), key=lambda x: -(x['income'] + x['expenses']))

    return jsonify({
        'currency': currency,
        'from_date': from_date,
        'to_date': to_date,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'balance': round(total_income - total_expenses, 2),
        'by_month': by_month,
        'by_category': by_category,
    })
