import os, sys, tempfile
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ['SIGHTLINE_CATALOG'] = 'sample_catalog.json'
os.environ['SIGHTLINE_NO_LLM'] = '1'  # unit tests never call Gemini
os.environ['SIGHTLINE_DB'] = os.path.join(tempfile.mkdtemp(), 'test.db')  # never the real ledger
os.environ['SIGHTLINE_UNDO_SECONDS'] = '0'  # capture right after the PIN unless a test opens the undo window

from app import checkout, paypal  # noqa: E402


class FakePayPal:
    """Answers like the sandbox does for AUTHORIZE orders with a vault_id. Replays on a repeated request id."""

    def __init__(self):
        self.calls, self.seen = [], {}

    def create_hold(self, vault_id, items, shipping, tax, request_id):
        self.calls.append(('hold', request_id))
        if request_id in self.seen:
            return self.seen[request_id]
        item_total = sum(i['unit_amount'] * i['quantity'] for i in items)
        usd = lambda d: {'currency_code': 'USD', 'value': f'{d:.2f}'}
        n = len(self.seen) + 1
        order = {'id': f'ORDER{n}', 'status': 'COMPLETED', 'purchase_units': [{
            'amount': {**usd(item_total + shipping + tax),
                       'breakdown': {'item_total': usd(item_total), 'shipping': usd(shipping), 'tax_total': usd(tax)}},
            'items': [{'name': i['name'], 'quantity': str(i['quantity']), 'unit_amount': usd(i['unit_amount'])} for i in items],
            'payments': {'authorizations': [{'id': f'AUTH{n}', 'status': 'CREATED', 'amount': usd(item_total + shipping + tax)}]}}]}
        self.seen[request_id] = order
        return order

    def capture(self, auth_id, request_id):
        self.calls.append(('capture', request_id))
        order = next(o for o in self.seen.values() if paypal.authorization_id(o) == auth_id)
        return {'id': 'CAP-' + auth_id, 'status': 'COMPLETED', 'amount': order['purchase_units'][0]['amount']}

    def refund(self, capture_id, amount, request_id, note):
        self.calls.append(('refund', request_id))
        return {'id': 'REF-' + request_id[:6], 'status': 'COMPLETED', 'amount': {'currency_code': 'USD', 'value': f'{amount:.2f}'}}

    def get_order(self, order_id):
        return {'id': order_id, 'status': 'COMPLETED'}

    def void(self, auth_id, request_id):
        self.calls.append(('void', request_id))
        return {}

    def count(self, kind):
        return len({rid for k, rid in self.calls if k == kind})  # distinct request ids = distinct real actions


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakePayPal()
    for name in ('create_hold', 'capture', 'void', 'get_order', 'refund'):
        monkeypatch.setattr(paypal, name, getattr(f, name))
    monkeypatch.setenv('DEMO_VAULT_ID', 'TEST-VAULT')
    monkeypatch.setenv('SIGHTLINE_DB', str(tmp_path / 'ledger.db'))
    checkout.LEDGER.clear()
    return f


@pytest.fixture
def client(fake):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def say(r):
    j = r.json()
    return ' '.join([j['say'], *j['lines']])


D = Decimal
