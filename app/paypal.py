"""PayPal sandbox REST calls (from spike_paypal.py). Money moves only through this file, never through an LLM tool.

Every write takes a request_id (PayPal-Request-Id), so a repeated call replays instead of acting twice.
"""
import os, time, uuid

import httpx

API = os.environ.get('PAYPAL_API', 'https://api-m.sandbox.paypal.com')
_tok = {'value': None, 'exp': 0}


class PayPalError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body
        name = body.get('name') or body.get('error') or 'error' if isinstance(body, dict) else 'error'
        super().__init__(f'PayPal {status}: {name}')


def _token():
    if _tok['value'] and time.time() < _tok['exp'] - 60:
        return _tok['value']
    r = httpx.post(f'{API}/v1/oauth2/token', data={'grant_type': 'client_credentials'},
                   auth=(os.environ['PAYPAL_CLIENT_ID'], os.environ['PAYPAL_CLIENT_SECRET']), timeout=30)
    r.raise_for_status()
    j = r.json()
    _tok.update(value=j['access_token'], exp=time.time() + j.get('expires_in', 300))
    return _tok['value']


def _call(method, path, body=None, request_id=None):
    h = {'Authorization': f'Bearer {_token()}', 'Content-Type': 'application/json',
         'Prefer': 'return=representation', 'PayPal-Request-Id': request_id or str(uuid.uuid4())}
    r = httpx.request(method, f'{API}{path}', json=body, headers=h, timeout=30)
    if r.status_code >= 400:
        try:
            raise PayPalError(r.status_code, r.json())
        except ValueError:
            raise PayPalError(r.status_code, {'name': r.text[:200]})
    return r.json() if r.content else {}


def link_start(return_url, cancel_url):
    """Returns (setup_token_id, approve_url). The approve URL is a full-page PayPal login, no popup."""
    j = _call('POST', '/v3/vault/setup-tokens', {'payment_source': {'paypal': {
        'description': 'Sightline voice shopping', 'usage_pattern': 'IMMEDIATE', 'usage_type': 'MERCHANT',
        'customer_type': 'CONSUMER', 'permit_multiple_payment_tokens': False,
        'experience_context': {'brand_name': 'Sightline', 'shipping_preference': 'NO_SHIPPING',
                               'return_url': return_url, 'cancel_url': cancel_url}}}})
    return j['id'], next(l['href'] for l in j['links'] if l['rel'] == 'approve')


def link_return(setup_token):
    """Exchange the approved setup token for (vault_id, customer_id)."""
    j = _call('POST', '/v3/vault/payment-tokens', {'payment_source': {'token': {'id': setup_token, 'type': 'SETUP_TOKEN'}}})
    return j['id'], j.get('customer', {}).get('id')


def create_hold(vault_id, items, shipping, tax, request_id, description=None):
    """items: [{'name', 'quantity', 'unit_amount'}] with Decimal amounts. Creates an AUTHORIZE order (money held,
    not moved) and returns PayPal's order JSON, whose amount.breakdown is what the Readback speaks."""
    s = lambda d: f'{d:.2f}'
    item_total = sum(i['unit_amount'] * i['quantity'] for i in items)
    total = item_total + shipping + tax
    usd = lambda d: {'currency_code': 'USD', 'value': s(d)}
    body = {'intent': 'AUTHORIZE',
            'purchase_units': [{
                'amount': {**usd(total), 'breakdown': {'item_total': usd(item_total), 'shipping': usd(shipping),
                                                       'tax_total': usd(tax)}},
                'items': [{'name': i['name'][:127], 'quantity': str(i['quantity']), 'unit_amount': usd(i['unit_amount']),
                           'category': 'PHYSICAL_GOODS'} for i in items],
                **({'description': description[:127]} if description else {})}],
            'payment_source': {'paypal': {'vault_id': vault_id}}}
    return _call('POST', '/v2/checkout/orders', body, request_id)


def authorization_id(order):
    return order['purchase_units'][0]['payments']['authorizations'][0]['id']


def capture(auth_id, request_id):
    return _call('POST', f'/v2/payments/authorizations/{auth_id}/capture', {}, request_id)


def void(auth_id, request_id):
    return _call('POST', f'/v2/payments/authorizations/{auth_id}/void', None, request_id)


def refund(capture_id, amount, request_id, note):
    """Partial or full refund of a capture. amount: Decimal. Returns PayPal's refund (id, status, amount)."""
    return _call('POST', f'/v2/payments/captures/{capture_id}/refund',
                 {'amount': {'currency_code': 'USD', 'value': f'{amount:.2f}'}, 'note_to_payer': note[:255]}, request_id)


def get_order(order_id):
    return _call('GET', f'/v2/checkout/orders/{order_id}')


def get_authorization(auth_id):
    return _call('GET', f'/v2/payments/authorizations/{auth_id}')
