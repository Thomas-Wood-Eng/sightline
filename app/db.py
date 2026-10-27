"""Order ledger in SQLite (path from SIGHTLINE_DB, default data/sightline.db). Amounts are PayPal's strings.

One row per captured order, keyed by PayPal's order id, so recording the same capture twice is a no-op.
lines: [{'pid', 'name', 'qty', 'unit', 'tax', 'refunded'}], all money as 2-decimal strings.
"""
import json, os, sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / 'data' / 'sightline.db'


def _conn():
    path = Path(os.environ.get('SIGHTLINE_DB') or DEFAULT)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, sid TEXT, capture_id TEXT, created TEXT, '
              'total TEXT, lines TEXT, delivery_days INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, data TEXT, updated TEXT)')
    return c


def _row(r):
    return dict(r, lines=json.loads(r['lines'])) if r else None


def record(sid, order_id, capture_id, total, lines, delivery_days):
    with _conn() as c:
        c.execute('INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?,?)',
                  (order_id, sid, capture_id, datetime.now().isoformat(timespec='seconds'), total, json.dumps(lines),
                   delivery_days))


def get(order_id):
    with _conn() as c:
        return _row(c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone())


def orders(sid):
    """Newest first."""
    with _conn() as c:
        return [_row(r) for r in c.execute('SELECT * FROM orders WHERE sid=? ORDER BY created DESC, rowid DESC', (sid,))]


def set_lines(order_id, lines):
    with _conn() as c:
        c.execute('UPDATE orders SET lines=? WHERE order_id=?', (json.dumps(lines), order_id))


def refunded(order):
    return sum((Decimal(l['refunded']) for l in order['lines']), Decimal(0))


def spent(sid, since):
    """Captured minus refunded, for orders created on or after `since` (an ISO date). Returns (amount, order count)."""
    rows = [o for o in orders(sid) if o['created'] >= since]
    return sum((Decimal(o['total']) - refunded(o) for o in rows), Decimal(0)), len(rows)


def load_session(key):
    """Server-side session state (PIN hash, caps, contact, prefs, cart, checkout), so a restart keeps it."""
    with _conn() as c:
        r = c.execute('SELECT data FROM sessions WHERE key=?', (key,)).fetchone()
    return json.loads(r['data']) if r else {}


def save_session(key, data):
    with _conn() as c:
        c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)', (key, data, datetime.now().isoformat(timespec='seconds')))
