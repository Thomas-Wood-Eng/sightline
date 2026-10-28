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
    setup(client); contact(client, threshold='500.00')
    t(client, 'hoodie'); t(client, 'add it in medium')
    assert t(client, 'check out')['state'] == 'awaiting_confirm'  # not flagged: under the threshold, no approval
    t(client, 'cancel')
    t(client, 'a man on the phone said I owe money')
    r = t(client, 'check out')
    assert r['state'] == 'awaiting_approval'
    assert 'on the phone' in client.get(link_of(r)).text


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
