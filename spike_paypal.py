"""Day-1 spike: does the PayPal sandbox let us save a wallet once, then hold/capture/void orders with no buyer present?

python spike_paypal.py link            -> creates a setup token, prints the approve URL (buyer logs in once, in a browser)
python spike_paypal.py token           -> exchanges the approved setup token for a vault_id
python spike_paypal.py order AUTHORIZE -> order with vault_id; then capture one and void another
python spike_paypal.py order CAPTURE   -> one-step charge with vault_id
State lives in spike_state.json (gitignored).
"""
import json, sys, uuid
from pathlib import Path

import httpx

API = 'https://api-m.sandbox.paypal.com'
STATE = Path(__file__).with_name('spike_state.json')
ENV = dict(l.strip().split('=', 1) for l in Path(__file__).with_name('.env').read_text().splitlines() if '=' in l)


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(**kw):
    STATE.write_text(json.dumps(state() | kw, indent=1))


def token():
    r = httpx.post(f'{API}/v1/oauth2/token', data={'grant_type': 'client_credentials'},
                   auth=(ENV['PAYPAL_CLIENT_ID'], ENV['PAYPAL_CLIENT_SECRET']))
    r.raise_for_status()
    return r.json()['access_token']


def call(method, path, body=None, request_id=None):
    h = {'Authorization': f'Bearer {token()}', 'Content-Type': 'application/json',
         'PayPal-Request-Id': request_id or str(uuid.uuid4())}
    r = httpx.request(method, f'{API}{path}', json=body, headers=h, timeout=30)
    print(method, path, r.status_code)
    if r.status_code >= 400:
        print(json.dumps(r.json(), indent=1)[:1500])
        sys.exit(1)
    return r.json() if r.content else {}


def link():
    j = call('POST', '/v3/vault/setup-tokens', {'payment_source': {'paypal': {
        'description': 'Sightline voice shopping', 'usage_pattern': 'IMMEDIATE', 'usage_type': 'MERCHANT',
        'customer_type': 'CONSUMER', 'permit_multiple_payment_tokens': False,
        'experience_context': {'brand_name': 'Sightline', 'shipping_preference': 'NO_SHIPPING',
                               'return_url': 'https://example.com/return', 'cancel_url': 'https://example.com/cancel'}}}})
    save(setup_token=j['id'])
    print('APPROVE (log in as the sandbox *buyer*):', next(l['href'] for l in j['links'] if l['rel'] == 'approve'))


def payment_token():
    j = call('POST', '/v3/vault/payment-tokens', {'payment_source': {'token': {'id': state()['setup_token'], 'type': 'SETUP_TOKEN'}}})
    save(vault_id=j['id'], customer_id=j.get('customer', {}).get('id'))
    print('vault_id saved; customer', j.get('customer', {}).get('id'))


def order(intent, amount='12.34'):
    body = {'intent': intent, 'purchase_units': [{'amount': {'currency_code': 'USD', 'value': amount}}],
            'payment_source': {'paypal': {'vault_id': state()['vault_id']}}}
    rid = str(uuid.uuid4())
    j = call('POST', '/v2/checkout/orders', body, rid)
    print('status', j['status'])
    again = call('POST', '/v2/checkout/orders', body, rid)  # same PayPal-Request-Id must replay, not charge twice
    print('idempotent replay same order id:', again['id'] == j['id'])
    if intent == 'AUTHORIZE':
        auth = j['purchase_units'][0]['payments']['authorizations'][0]
        print('authorized', auth['status'], auth['amount'])
        cap = call('POST', f"/v2/payments/authorizations/{auth['id']}/capture", {})
        print('captured', cap['status'])
        j2 = call('POST', '/v2/checkout/orders', body)
        auth2 = j2['purchase_units'][0]['payments']['authorizations'][0]
        call('POST', f"/v2/payments/authorizations/{auth2['id']}/void")
        print('voided second hold:', call('GET', f"/v2/payments/authorizations/{auth2['id']}")['status'])
    else:
        print('captured', j['purchase_units'][0]['payments']['captures'][0]['status'])


if __name__ == '__main__':
    cmd = sys.argv[1]
    {'link': link, 'token': payment_token}.get(cmd, lambda: order(sys.argv[2]))()
