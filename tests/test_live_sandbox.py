"""Opt-in: SIGHTLINE_LIVE=1 python -m pytest tests/test_live_sandbox.py  (real PayPal sandbox, spike vault_id)."""
import json, os, uuid
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(os.environ.get('SIGHTLINE_LIVE') != '1', reason='live sandbox test; set SIGHTLINE_LIVE=1')


@pytest.fixture(scope='module')
def pp():
    import app.main  # noqa: F401  loads .env
    from app import paypal
    return paypal


def hold(pp):
    vault = json.loads((ROOT / 'spike_state.json').read_text())['vault_id']
    items = [{'name': 'Live test item', 'quantity': 2, 'unit_amount': Decimal('3.50')}]
    rid = uuid.uuid4().hex
    order = pp.create_hold(vault, items, Decimal('1.00'), Decimal('0.35'), rid + '-hold')
    assert order['purchase_units'][0]['amount']['value'] == '8.35'
    assert order['purchase_units'][0]['amount']['breakdown']['tax_total']['value'] == '0.35'
    again = pp.create_hold(vault, items, Decimal('1.00'), Decimal('0.35'), rid + '-hold')
    assert again['id'] == order['id']  # idempotent replay
    return pp.authorization_id(order), rid


def test_hold_then_capture(pp):
    auth, rid = hold(pp)
    cap = pp.capture(auth, rid + '-capture')
    assert cap['status'] == 'COMPLETED' and cap['amount']['value'] == '8.35'
    assert pp.capture(auth, rid + '-capture')['id'] == cap['id']  # repeated confirm: same capture


def test_hold_then_void(pp):
    auth, rid = hold(pp)
    pp.void(auth, rid + '-void')
    assert pp.get_authorization(auth)['status'] == 'VOIDED'
