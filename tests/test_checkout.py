from decimal import Decimal

from app import catalog
from conftest import say


def setup(client, pin='1234', order_cap='100.00', daily_cap='250.00'):
    r = client.post('/api/onboarding', json={'screen_reader': True, 'pin': pin, 'per_order_cap': order_cap, 'daily_cap': daily_cap})
    assert r.status_code == 200, r.text


def t(client, text):
    r = client.post('/api/turn', json={'text': text})
    assert r.status_code == 200, r.text
    return r.json()


def to_readback(client):
    setup(client)
    t(client, 'hoodie')
    t(client, 'add number 1')
    return t(client, 'check out')


def test_readback_numbers_come_from_paypal(client, fake):
    r = to_readback(client)
    assert r['state'] == 'awaiting_confirm'
    order = next(iter(fake.seen.values()))
    bd = order['purchase_units'][0]['amount']['breakdown']
    text = ' '.join(r['lines'])
    for v in (bd['shipping']['value'], bd['tax_total']['value'], order['purchase_units'][0]['amount']['value']):
        assert f'{v} US dollars' in text
    # fixed order: item, quantity, unit price, shipping, tax, total, delivery, seller
    keys = ['Item 1', 'Quantity', 'Unit price', 'Shipping', 'Tax', 'Total', 'Delivery by', 'Seller']
    pos = [text.index(k) for k in keys]
    assert pos == sorted(pos)
    p = catalog.search('hoodie')[0]
    tax = (Decimal(str(p['price'])) * Decimal('0.05')).quantize(Decimal('0.01'))
    assert bd['tax_total']['value'] == f'{tax:.2f}'


def test_confirm_pin_capture(client, fake):
    to_readback(client)
    assert t(client, 'confirm')['state'] == 'awaiting_pin'
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['state'] == 'captured' and 'Paid' in r['say']
    assert fake.count('capture') == 1
    assert t(client, 'cart')['say'] == 'Your cart is empty.'


def test_confirm_twice_one_capture(client, fake):
    to_readback(client)
    t(client, 'confirm')
    t(client, 'confirm')
    stale = dict(client.cookies)  # replaying an old cookie must not charge twice either
    client.post('/api/pin', json={'pin': '1234'})
    client.post('/api/pin', json={'pin': '1234'})
    assert t(client, 'confirm')['say'].startswith('Already paid')
    client.cookies.clear()
    client.cookies.update(stale)
    client.post('/api/pin', json={'pin': '1234'})
    assert fake.count('capture') == 1  # same PayPal-Request-Id each time, so PayPal replays


def test_cancel_voids(client, fake):
    to_readback(client)
    r = t(client, 'cancel')
    assert r['state'] == 'voided' and 'released' in r['say']
    assert fake.count('void') == 1 and fake.count('capture') == 0
    assert 'quantity 1' in ' '.join(t(client, 'cart')['lines'])  # cart kept


def test_cancel_at_pin_step_voids(client, fake):
    to_readback(client)
    t(client, 'confirm')
    assert t(client, 'no')['state'] == 'voided'
    assert fake.count('void') == 1


def test_pin_lockout_voids(client, fake):
    to_readback(client)
    t(client, 'confirm')
    assert '2 tries left' in client.post('/api/pin', json={'pin': '0000'}).json()['say']
    assert '1 try left' in client.post('/api/pin', json={'pin': '1111'}).json()['say']
    r = client.post('/api/pin', json={'pin': '2222'}).json()
    assert r['state'] == 'voided' and 'locked' in r['say']
    assert fake.count('void') == 1 and fake.count('capture') == 0
    assert 'locked' in t(client, 'check out')['say']
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'voided'


def test_pin_tries_survive_cookie_replay(client, fake):
    to_readback(client)
    t(client, 'confirm')
    stale = dict(client.cookies)
    for pin in ('0000', '1111'):
        client.cookies.clear(); client.cookies.update(stale)
        client.post('/api/pin', json={'pin': pin})
    client.cookies.clear(); client.cookies.update(stale)
    assert 'locked' in client.post('/api/pin', json={'pin': '2222'}).json()['say']


def test_pin_typed_in_message_box_is_refused(client, fake):
    to_readback(client)
    t(client, 'confirm')
    r = t(client, '1234')
    assert 'PIN box' in r['say'] and r['state'] == 'awaiting_pin'
    assert fake.count('capture') == 0


def test_free_text_blocked_while_holding(client, fake):
    to_readback(client)
    r = t(client, 'find me a mug')
    assert 'on hold' in r['say'] and r['state'] == 'awaiting_confirm'


def test_per_order_cap_refusal(client, fake):
    setup(client, order_cap='50.00')
    t(client, 'hoodie'); t(client, 'add 2 of number 1')
    r = t(client, 'check out')
    assert r['state'] == 'idle' and fake.count('hold') == 0
    # 2 x 34.99 + 4.99 shipping + 3.50 tax = 78.47; cap 50.00; over by 28.47
    assert 'per-order cap is 50.00 US dollars' in r['say'] and '28.47 US dollars over' in r['say']


def test_daily_cap_refusal(client, fake):
    setup(client, order_cap='100.00', daily_cap='60.00')
    t(client, 'hoodie'); t(client, 'add it'); t(client, 'check out'); t(client, 'confirm')
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'
    t(client, 'hoodie'); t(client, 'add it')
    r = t(client, 'check out')
    assert 'daily cap is 60.00 US dollars' in r['say'] and fake.count('hold') == 1


def test_caps_not_changeable_by_voice_or_without_pin(client, fake):
    setup(client)
    assert 'cannot be changed by voice' in t(client, 'raise my cap to 5000')['say']
    assert client.post('/api/settings', json={'per_order_cap': '5000'}).status_code == 403
    r = client.post('/api/settings', json={'per_order_cap': '150', 'current_pin': '1234'})
    assert r.json()['per_order_cap'] == '150.00'


def test_checkout_needs_pin_and_cart(client, fake):
    assert 'empty' in t(client, 'check out')['say']
    t(client, 'hoodie'); t(client, 'add it')
    assert 'PIN' in t(client, 'check out')['say'] and fake.count('hold') == 0
