"""Tests for the second feature batch: scam guard, package photo check, Pay in 4, disputes, compare,
price-drop alerts, purchase history."""
from app import checkout
from test_checkout import setup, t
from test_features import contact


# ---- 1. gift-card / pressure scam guard ----
def link_of(r):
    return next(l for l in r['lines'] if l.startswith('Approval link: '))[len('Approval link: '):]


def test_pressure_words_warn_and_flag(client, fake):
    setup(client)
    r = t(client, 'The IRS called and told me to pay a fine today')
    assert r['say'].startswith('This matches a common scam.') and 'never ask for gift cards' in r['say']
    assert 'no trusted contact yet' in r['say'] and r['lines'] == []
    for said in ('my grandson is in trouble and needs bail', 'someone on the phone told me to buy bitcoin',
                 'they said keep it a secret', 'I won the lottery and need to pay the processing fee'):
        assert t(client, said)['say'].startswith('This matches a common scam.'), said
    assert not t(client, 'warm hoodie')['say'].startswith('This matches')


def test_gift_card_without_contact_is_refused(client, fake):
    setup(client)
    r = t(client, 'find me a gift card')
    assert r['say'].startswith('A note first: gift cards are the most common way scammers')
    assert 'Sightline Demo Store gift card' in r['lines'][0]
    assert not t(client, 'gift card')['say'].startswith('A note first')  # said once, not every time
    assert 'Added' in t(client, 'add number 1')['say']
    r = t(client, 'check out')
    assert r['say'].startswith('Not placed.') and 'open Settings, fill in Trusted contact' in r['say']
    assert r['state'] == 'idle' and fake.count('hold') == 0


def test_gift_card_always_needs_contact_with_reason(client, fake):
    setup(client); contact(client, threshold='500.00')  # far above the order: only the guard asks for approval
    scam_hold(client, True)
    t(client, 'my bank says I must buy gift cards urgently')
    t(client, 'gift card'); t(client, 'add number 1')
    r = t(client, 'check out')
    assert r['state'] == 'awaiting_approval' and 'flagged it as a possible gift-card scam' in ' '.join(r['lines'])
    assert any('gift cards are a common scam payment' in l for l in r['lines'])  # also in the Readback
    page = client.get(link_of(r)).text
    assert 'Sightline flagged this as a possible gift-card scam: &quot;my bank says I must buy gift cards urgently&quot;' in page
    client.post(link_of(r) + '/approve')
    assert t(client, 'confirm')['state'] == 'awaiting_pin'
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'


def test_flagged_session_needs_contact_for_any_order(client, fake):
    setup(client); contact(client, threshold='500.00'); scam_hold(client, True)
    t(client, 'hoodie'); t(client, 'add it in medium')
    assert t(client, 'check out')['state'] == 'awaiting_confirm'  # not flagged: under the threshold, no approval
    t(client, 'cancel')
    t(client, 'a man on the phone said I owe money')
    r = t(client, 'check out')
    assert r['state'] == 'awaiting_approval'
    assert 'on the phone' in client.get(link_of(r)).text


def scam_hold(client, on):
    body = {'contact_name': 'Alex', 'contact_email': 'alex@example.com', 'approval_threshold': '500.00', 'scam_hold': on}
    assert client.post('/api/settings', json=body).status_code == 403  # like the contact: only with the current PIN
    return client.post('/api/settings', json={**body, 'current_pin': '1234'}).json()


def test_scam_hold_off_by_default_and_worded_as_the_shoppers_choice(client, fake):
    setup(client); contact(client, threshold='500.00')
    assert client.get('/api/settings').json()['contact']['scam_hold'] is False  # the shopper turns it on
    assert scam_hold(client, True)['saved'] == 'Settings saved: Alex asked when a scam is suspected.'
    assert 'If Sightline suspects a scam, ask my trusted contact before paying</label>' in client.get('/').text
    assert 'and orders Sightline flags as a possible scam' in t(client, 'settings')['say']
    assert 'Because you chose it in Settings, your next payment goes ahead only if Alex approves it.' in         t(client, 'find me a gift card')['say']  # the gift card note, said once
    r = t(client, 'The IRS called and told me to pay a fine today')
    assert ('Because you chose it in Settings, your next payment goes ahead only if Alex approves it. '
            'It is OK to hang up') in r['say']


def test_scam_hold_off_warns_then_the_usual_steps(client, fake):
    setup(client); contact(client, threshold='500.00'); scam_hold(client, True)
    v = scam_hold(client, False)
    assert v['contact']['scam_hold'] is False and v['saved'] == 'Settings saved: Alex not asked when a scam is suspected.'
    assert 'orders flagged as a possible scam do not wait for Alex' in t(client, 'settings')['say']
    assert 'gift cards. Take a moment before you confirm.' in t(client, 'gift card')['say']
    r = t(client, 'my bank says I must buy gift cards urgently')
    assert r['say'].startswith('This matches a common scam.') and 'Take a moment before you confirm.' in r['say']
    assert 'approves' not in r['say'] and 'no trusted contact' not in r['say']
    t(client, 'gift card'); t(client, 'add number 1')
    r = t(client, 'check out')  # a gift card, in a flagged session, under the approval amount: no approval
    assert r['state'] == 'awaiting_confirm' and not any(l.startswith('Approval link') for l in r['lines'])
    assert any('gift cards are a common scam payment' in l for l in r['lines'])  # still warned in the Readback
    t(client, 'confirm')
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'
    assert scam_hold(client, True)['saved'] == 'Settings saved: Alex asked when a scam is suspected.'


def test_scam_hold_off_never_quotes_the_shopper(client, fake):
    setup(client); contact(client, threshold='20.00')
    client.post('/api/settings', json={'contact_name': 'Alex', 'contact_email': 'alex@example.com',
                                       'approval_threshold': '20.00', 'scam_hold': False, 'current_pin': '1234'})
    t(client, 'a man on the phone said I owe money')
    t(client, 'hoodie'); t(client, 'add it in medium')
    r = t(client, 'check out')  # over the approval amount: the contact is asked, for the amount
    assert r['state'] == 'awaiting_approval' and 'over your approval amount of 20.00 US dollars' in ' '.join(r['lines'])
    page = client.get(link_of(r)).text
    assert 'possible gift-card scam: they had a scam warning from Sightline earlier' in page and 'on the phone' not in page


def test_gift_note_is_not_a_scam_cue(client, fake):
    setup(client); contact(client, threshold='500.00')
    t(client, 'hoodie'); t(client, "it's a gift")
    assert t(client, 'keep it a secret from mum')['say'].startswith('Gift note saved')
    t(client, 'add it in medium')
    assert t(client, 'check out')['state'] == 'awaiting_confirm'  # not flagged, so no approval needed


# ---- 2. "is this my package?" photo check (Gemini mocked) ----
from pathlib import Path  # noqa: E402

from app import llm  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / 'demo' / 'assets'


def buy(client, what='mug', add='add it'):
    t(client, what); t(client, add); t(client, 'check out'); t(client, 'confirm')
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'


def photo(client, name):
    return client.post('/api/package', content=(DEMO / name).read_bytes(), headers={'Content-Type': 'image/jpeg'})


def test_package_check_match_and_mismatch(client, fake, monkeypatch):
    seen = []
    answers = iter(['{"match": "yes", "item": "Insulated travel mug", "seen": "a black travel mug"}',
                    '```json\n{"match": "no", "item": "", "seen": "an orange hooded rain jacket"}\n```'])
    monkeypatch.delenv('SIGHTLINE_NO_LLM')
    monkeypatch.setattr(llm, 'vision', lambda prompt, image, mime: seen.append((prompt, mime, len(image))) or next(answers))
    setup(client); buy(client)
    r = t(client, 'check my package')
    assert r['action'] == 'photo' and 'Insulated travel mug' in r['say'] and 'does not keep it' in r['say']
    r = photo(client, 'package_mismatch.jpg').json()  # the mug photo, for a mug order
    assert r['say'].startswith('Photo suggests this matches: Insulated travel mug, matte black.')
    assert 'Insulated travel mug, matte black' in seen[0][0] and 'leak-proof' not in seen[0][0]  # catalogue photo text, not listing
    assert seen[0][1] == 'image/jpeg' and seen[0][2] > 1000
    r = photo(client, 'package_match.jpg').json()
    assert r['say'] == ('Photo suggests this may not match: you ordered Insulated travel mug, matte black, the photo looks '
                        'like an orange hooded rain jacket. Say return it to start a return.')
    r = t(client, 'return it')
    assert r['state'] == 'awaiting_confirm' and 'Return: Insulated travel mug' in ' '.join(r['lines'])


def test_package_check_boundary_and_fallback(client, fake, monkeypatch):
    setup(client)
    assert 'no orders to check' in photo(client, 'package_match.jpg').json()['say']
    buy(client)
    r = client.post('/api/package', content=b'not a photo at all', headers={'Content-Type': 'image/jpeg'})
    assert r.status_code == 415 and 'JPEG, PNG, WebP or HEIC' in r.json()['detail']
    r = client.post('/api/package', content=b'\xff\xd8\xff' + b'0' * (10 * 1024 * 1024), headers={'Content-Type': 'image/jpeg'})
    assert r.status_code == 413
    # SIGHTLINE_NO_LLM (as when Gemini is down): an honest fallback, never a guess
    r = photo(client, 'package_match.jpg').json()
    assert r['say'].startswith('I could not check the photo just now, and nothing was kept. You ordered Insulated travel mug')
    monkeypatch.delenv('SIGHTLINE_NO_LLM')
    monkeypatch.setattr(llm, 'vision', lambda *a: None)
    assert photo(client, 'package_match.jpg').json()['say'].startswith('I could not check the photo')
    monkeypatch.setattr(llm, 'vision', lambda *a: '{"match": "unsure", "seen": "a closed cardboard box"}')
    assert photo(client, 'package_match.jpg').json()['say'].startswith('The photo is unclear')


# ---- 3. PayPal Pay in 4, read aloud, never chosen for the shopper ----
def test_pay_in_4_line_only_in_range():
    from app import speech
    order = lambda v: {'purchase_units': [{'amount': {'currency_code': 'USD', 'value': v, 'breakdown': {
        'item_total': {'value': v}, 'shipping': {'value': '0.00'}, 'tax_total': {'value': '0.00'}}}, 'items': []}]}
    lines = speech.readback(order('41.73'), {'delivery_days': 3, 'seller': 'Demo'})[1]
    assert lines[-2] == 'PayPal Pay in 4 may be available: 4 payments of about 10.43 US dollars. Say pay later to hear more.'
    lines = speech.readback(order('60.00'), {'delivery_days': 3, 'seller': 'Demo'})[1]
    assert 'PayPal Pay in 4 may be available: 4 payments of 15.00 US dollars.' in lines[-2]
    for v in ('29.99', '1500.01'):
        assert not any('Pay in 4' in l for l in speech.readback(order(v), {'delivery_days': 3, 'seller': 'Demo'})[1])


def test_pay_later_explains_and_never_changes_the_payment(client, fake):
    setup(client)
    assert t(client, 'hoodie')  # 41.73 with shipping and tax
    t(client, 'add it in medium')
    r = t(client, 'check out')
    assert any(l.startswith('PayPal Pay in 4 may be available: 4 payments of about 10.43 US dollars') for l in r['lines'])
    for said in ('pay later', 'tell me about pay in 4', 'what is paypal pay in four'):
        r = t(client, said)
        assert 'interest-free' in r['say'] and "Sightline pays in full" in r['say'] and r['state'] == 'awaiting_confirm'
    assert 'To pay this order in full, say confirm' in r['say']
    t(client, 'confirm')
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['state'] == 'captured' and 'captured 41.73 US dollars' in r['say']  # the full amount, one capture
    assert fake.count('capture') == 1
    assert 'interest-free' in t(client, 'pay later')['say']  # also outside a checkout


# ---- 4. dispute help by voice ----
def test_dispute_parse():
    from app.lane0 import parse
    assert parse('I never got my order')[:2] == ('dispute', 'missing')
    assert parse('my mug never arrived')[:2] == ('dispute', 'missing')
    assert parse('it arrived broken')[:2] == ('dispute', 'broken')
    assert parse("this isn't what I ordered")[:2] == ('dispute', 'wrong')
    assert parse('they sent me the wrong item')[:2] == ('dispute', 'wrong')
    assert parse('has my order arrived') == ('track', '')
    assert parse('that is wrong') == ('wrong',)  # feedback, not a dispute


def test_dispute_explains_then_offers_the_usual_refund(client, fake):
    setup(client)
    buy(client)
    r = t(client, 'it arrived broken')
    assert r['say'].startswith('Sorry it arrived broken. PayPal Purchase Protection covers eligible items')
    assert 'within 180 days' in r['say'] and r['state'] == 'captured'
    assert r['lines'][0].startswith('Do you want a refund for Insulated travel mug')
    r = t(client, 'yes')  # the same refund Readback, confirm and PIN as a return
    assert r['state'] == 'awaiting_confirm' and 'Return: Insulated travel mug' in ' '.join(r['lines'])
    t(client, 'confirm')
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['say'].startswith('Refunded') and fake.count('refund') == 1
    r = t(client, 'I never got my order')
    assert 'not already refunded' in r['say'] and 'ask' not in r


def test_dispute_no_means_nothing_moves(client, fake):
    setup(client)
    buy(client)
    assert t(client, "this isn't what I ordered")['lines'][0].startswith('Do you want a refund')
    assert t(client, 'no')['say'].startswith('OK, no refund started')
    assert fake.count('refund') == 0


# ---- 5. compare: only the differences, from catalogue data ----
def test_compare_says_only_differences():
    from app import catalog, speech
    h, sw = catalog.get('hoodie-01'), catalog.get('sweater-01')
    say, lines = speech.compare([(1, h), (2, dict(h, id='h2'))])
    assert 'they are the same' in say and lines == []
    say, lines = speech.compare([(1, h), (2, dict(h, id='h2', price=30.0, delivery_days=h['delivery_days'] + 2))])
    assert say == 'Comparing 2 items, only what differs.'
    assert lines[0] == 'Cheapest: number 2, Fleece-lined pullover hoodie, $30.00.'
    assert lines[1].startswith('Arrives first: number 1, Fleece-lined pullover hoodie, ') and len(lines) == 2
    food = lambda i, a: dict(h, id=i, category='grocery', listing=dict(h['listing'], sizes=None, allergens=a))
    lines = speech.compare([(1, food('a', 'Contains peanuts.')), (2, food('b', None))])[1]
    assert lines[-1] == 'Allergens, listing says: number 1, Contains peanuts; number 2, not stated.'
    lines = speech.compare([(1, h), (2, sw)])[1]
    assert any(l.startswith('Sizes: number 1, S, M, L or XL; number 2,') for l in lines)


def test_compare_those_two(client, fake):
    from app.lane0 import parse
    assert parse('compare those two') == ('compare', [], 2) and parse('compare 1 and 2') == ('compare', [1, 2])
    setup(client)
    t(client, 'anything under 100')
    r = t(client, 'compare those two')
    assert r['say'] == 'Comparing 2 items, only what differs.' and 'number 3' not in ' '.join(r['lines'])
    assert t(client, 'which is better')['say'].startswith('Comparing 3 items')
    t(client, '1')
    assert t(client, 'compare it with number 3')['say'].startswith('Comparing 2 items')


# ---- 6. price-drop alerts on the wishlist ----
def test_alert_parse():
    from app.lane0 import parse
    assert parse('tell me if it gets cheaper') == ('alert', None, 'it')
    assert parse('alert me under 40 dollars') == ('alert', '40', 'it')
    assert parse('let me know when the hoodie drops below $29.50') == ('alert', '29.50', ('name', 'hoodie'))
    assert parse('tell me about it')[0] == 'describe'


def test_demo_price_endpoint_is_off_by_default(client, fake, monkeypatch):
    from app import catalog
    monkeypatch.delenv('SIGHTLINE_DEMO', raising=False)
    before = catalog.get('hoodie-01')['price']
    assert client.post('/api/demo/price', json={'id': 'hoodie-01', 'price': '1.00'}).status_code == 404
    assert catalog.get('hoodie-01')['price'] == before


def test_price_drop_alert_said_once(client, fake, monkeypatch):
    from app import catalog
    monkeypatch.setitem(catalog.get('hoodie-01'), 'price', catalog.get('hoodie-01')['price'])  # restored after the test
    monkeypatch.setenv('SIGHTLINE_DEMO', '1')
    setup(client)
    t(client, 'hoodie'); t(client, '1')
    r = t(client, 'alert me under 30 dollars')
    assert r['say'] == ('OK. I will tell you once if Fleece-lined pullover hoodie drops to $30.00 or less. '
                        'It is $34.99 now, and it is in your saved items.')
    assert 'Alert at $30.00 or less.' in t(client, 'my saved items')['lines'][0]
    assert t(client, 'alert me under 40 dollars')['say'].startswith('Fleece-lined pullover hoodie is already $34.99')
    assert client.post('/api/demo/price', json={'id': 'hoodie-01', 'price': '29.99'}).json()['price'] == '29.99'
    assert client.post('/api/demo/price', json={'id': 'nope', 'price': '5'}).status_code == 404
    r = t(client, 'cart')
    assert r['say'].startswith('Price drop: Fleece-lined pullover hoodie is now $29.99, at or under your alert of $30.00. '
                               'Say move the fleece-lined pullover hoodie to my cart')
    assert not t(client, 'cart')['say'].startswith('Price drop')  # once
    r = t(client, 'move the fleece-lined pullover hoodie to my cart')
    assert r['say'].startswith('Which size?')


def test_alert_without_amount_means_any_drop(client, fake, monkeypatch):
    from app import catalog
    monkeypatch.setitem(catalog.get('mug-01'), 'price', catalog.get('mug-01')['price'])
    setup(client)
    t(client, 'mug'); t(client, '1')
    assert 'gets cheaper than $18.50' in t(client, 'tell me if it gets cheaper')['say']
    catalog.get('mug-01')['price'] = 18.49
    assert t(client, 'help')['say'].startswith('Price drop: Insulated travel mug is now $18.49')


# ---- 7. what did I buy: from the order ledger, never the model ----
def test_purchase_history_by_period(client, fake):
    from datetime import date, timedelta
    from app import db
    from app.lane0 import parse
    assert parse('what did I buy last month') == ('spent', 'last_month', 'list')
    assert parse('what did I buy this week') == ('spent', 'week', 'list')
    assert parse('show my PayPal purchases') == ('spent', 'all', 'list')
    assert parse('how much did I spend last week') == ('spent', 'last_week')
    assert parse('what did I buy') == ('orders',)
    setup(client)
    buy(client)  # today: the mug
    sid = next(iter(checkout.LEDGER))
    first = date.today().replace(day=1)
    last_month = (first - timedelta(days=1)).replace(day=15).isoformat() + 'T10:00:00'
    db.record(sid, 'OLD1', 'CAP-OLD1', '41.73', [{'pid': 'hoodie-01', 'name': 'Fleece-lined pullover hoodie (size M)',
                                                  'qty': 1, 'unit': '34.99', 'tax': '1.75', 'refunded': '0.00'}], 3)
    with db._conn() as c:
        c.execute('UPDATE orders SET created=? WHERE order_id=?', (last_month, 'OLD1'))
    r = t(client, 'what did I buy last month')
    assert r['say'] == 'Last month, you spent 41.73 US dollars on 1 order, after refunds.'
    assert r['lines'] == [f"{speech_day(last_month)}: Fleece-lined pullover hoodie (size M). Paid 41.73 US dollars. "
                          'PayPal order OLD1.']
    r = t(client, 'show my PayPal purchases')
    assert r['say'].startswith('In total, you spent') and 'on 2 orders' in r['say'] and len(r['lines']) == 2
    assert 'Insulated travel mug' in r['lines'][0] and 'PayPal order ORDER1' in r['lines'][0]  # newest first
    assert 'on 1 order' in t(client, 'what did I buy this month')['say']


def speech_day(iso):
    from app import speech
    return speech._day(iso)
