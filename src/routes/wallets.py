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
