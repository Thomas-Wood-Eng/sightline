"""Tests for the post-MVP features (FEATURES.md)."""
from app import lane0
from app.lane0 import parse
from conftest import say
from test_checkout import setup, t


# ---- 1. sizes and variants ----
def test_parse_variants():
    assert parse('add it in medium') == ('add', 1, 'it', 'medium')
    assert parse('add number 2 in size L') == ('add', 1, ('n', 2), 'l')
    assert parse('add 2 of them in black') == ('add', 2, 'it', 'black')
    assert parse('the black one') == ('pick', ('name', 'black'))


def test_match_size():
    assert lane0.match_size('medium', ['S', 'M', 'L']) == 'M'
    assert lane0.match_size('extra large please', ['S', 'L', 'XL']) == 'XL'
    assert lane0.match_size('us nine', ['US 8', 'US 9']) == 'US 9'
    assert lane0.match_size('32 by 32', ['30x30', '32x32']) == '32x32'
    assert lane0.match_size('black', ['S', 'M']) is None


def test_add_asks_for_size_then_readback_has_it(client, fake):
    setup(client)
    t(client, 'hoodie')
    r = t(client, 'add it')
    assert r['say'].startswith('Which size?') and 'S, M, L or XL' in r['say']
    assert t(client, 'cart')['say'] == 'Your cart is empty.'
    t(client, 'add it')
    r = t(client, 'medium')
    assert 'Added: Fleece-lined pullover hoodie (size M, heather grey)' in r['say']
    assert '(size M, heather grey)' in ' '.join(t(client, 'cart')['lines'])
    rb = ' '.join(t(client, 'check out')['lines'])
    assert 'Item 1: Fleece-lined pullover hoodie (size M, heather grey).' in rb
    order = next(iter(fake.seen.values()))
    assert order['purchase_units'][0]['items'][0]['name'] == 'Fleece-lined pullover hoodie (size M, heather grey)'


def test_colour_choice(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, '1')
    assert t(client, 'the black one')['say'].startswith('Black chosen')
    assert '(size L, black)' in t(client, 'add it in large')['say']
    assert '(size S, navy blue)' in t(client, 'add the navy one in small')['say']
    assert '(size XL, heather grey), quantity 1. Cart has 3 items' in t(client, 'add it in extra large')['say']


def test_size_question_dropped_by_other_command(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it')
    assert t(client, 'cancel')['say'] == 'OK, not added.'
    t(client, 'add it')
    assert t(client, 'what is in my cart')['say'] == 'Your cart is empty.'


# ---- 2. saved preferences ----
def test_prefs_set_only_in_settings(client, fake):
    setup(client)
    r = client.post('/api/settings', json={'per_order_cap': '100.00', 'daily_cap': '250.00', 'verbosity': 'brief',
                                           'default_size': 'M', 'avoid_allergens': 'peanuts, Milk and eggs'})
    assert r.status_code == 200, r.text  # unchanged caps need no PIN
    p = r.json()['prefs']
    assert p['verbosity'] == 'brief' and p['size'] == 'M' and p['avoid'] == ['nuts', 'milk', 'eggs']
    assert client.post('/api/settings', json={'verbosity': 'loud'}).status_code == 422
    r = t(client, "I'm a size L, remember that")
    assert 'only be changed in the Settings form' in r['say'] and 'Default size M' in r['say']
    assert client.get('/api/settings').json()['prefs']['size'] == 'M'


def test_default_size_and_brief(client, fake):
    setup(client)
    client.post('/api/settings', json={'verbosity': 'brief', 'default_size': 'medium'})
    r = t(client, 'anything under 100')
    assert r['lines'][0].count('stars') == 0
    t(client, 'hoodie')
    assert '(size M, heather grey)' in t(client, 'add it')['say'] and 'default size' in t(client, 'repeat')['say']
    assert len(t(client, 'describe it')['lines']) == 1  # brief: what it is, then the price line


def test_simple_mode_one_result(client, fake):
    setup(client)
    client.post('/api/settings', json={'simple_mode': True})
    r = t(client, 'anything under 100')
    assert len(r['lines']) == 1
    assert len(t(client, 'more results')['lines']) == 1


def test_saved_allergens_filter_food_only():
    from app import lane1
    food = lambda i, a: {'id': i, 'category': 'grocery', 'listing': {'allergens': a}}
    items = [food('trail', 'Contains peanuts.'), food('tea', 'No major allergens declared.'), food('mystery', None),
             {'id': 'hoodie', 'category': 'clothing', 'listing': {'allergens': None}}]
    kept, note = lane1.saved_filter({'prefs': {'avoid': ['nuts']}}, items)
    assert [p['id'] for p in kept] == ['tea', 'hoodie'] and '2 items left out' in note
    assert lane1.saved_filter({}, items) == (items, '')


# ---- 3. undo window ----
def pin_with_undo(client, monkeypatch):
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '10')
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in medium'); t(client, 'check out'); t(client, 'confirm')
    return client.post('/api/pin', json={'pin': '1234'}).json()


def test_undo_voids_before_capture(client, fake, monkeypatch):
    r = pin_with_undo(client, monkeypatch)
    assert r['state'] == 'undo_window' and 'say undo' in r['say'] and 8 <= r['due_in'] <= 10
    assert client.post('/api/finalize').json()['state'] == 'undo_window'  # too early: nothing captured
    stale = dict(client.cookies)
    r = t(client, 'undo')
    assert r['say'].startswith('Undone. Nothing was charged.') and r['state'] == 'voided'
    assert fake.count('void') == 1 and fake.count('capture') == 0
    client.cookies.clear(); client.cookies.update(stale)  # an old cookie cannot resurrect the undone payment
    import time as _time
    monkeypatch.setattr(_time, 'time', lambda real=_time.time: real() + 11)
    assert 'undone' in client.post('/api/finalize').json()['say'] and fake.count('capture') == 0


def test_capture_after_window_is_idempotent(client, fake, monkeypatch):
    pin_with_undo(client, monkeypatch)
    assert 'Paying in' in t(client, 'what is in my cart')['say']
    import time as _time
    monkeypatch.setattr(_time, 'time', lambda real=_time.time: real() + 11)
    stale = dict(client.cookies)
    r = client.post('/api/finalize').json()
    assert r['state'] == 'captured' and r['say'].startswith('Paid.')
    assert t(client, 'undo')['say'].startswith('Too late')
    client.cookies.clear(); client.cookies.update(stale)
    client.post('/api/finalize')
    assert fake.count('capture') == 1 and fake.count('void') == 0


# ---- 4. trusted contact ----
def contact(client, threshold='20.00'):
    body = {'contact_name': 'Alex', 'contact_email': 'alex@example.com', 'approval_threshold': threshold}
    assert client.post('/api/settings', json=body).status_code == 403  # needs the current PIN
    assert client.post('/api/settings', json={**body, 'current_pin': '1234'}).json()['contact']['name'] == 'Alex'


def to_approval(client):
    setup(client); contact(client)
    t(client, 'hoodie'); t(client, 'add it in medium')
    r = t(client, 'check out')
    link = next(l for l in r['lines'] if l.startswith('Approval link: '))[len('Approval link: '):]
    return r, link


def test_approval_then_confirm_and_pin(client, fake):
    r, link = to_approval(client)
    text = ' '.join(r['lines'])
    assert r['state'] == 'awaiting_approval' and 'Sent to Alex for approval' in text
    assert 'over your approval amount of 20.00 US dollars' in text and 'instead of emailed' in text
    assert 'Still waiting for Alex' in t(client, 'confirm')['say']
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'awaiting_approval'
    page = client.get(link).text
    assert 'Total: 41.73 US dollars.' in page and 'Approve this order' in page
    assert 'Approval link not valid' in client.get(link[:-2] + 'xx').text  # tampered signature
    assert 'Approved' in client.post(link + '/approve').text
    assert 'Already answered' in client.post(link + '/approve').text  # single use
    r = t(client, 'what now')
    assert r['say'].startswith('Alex approved') and r['state'] == 'awaiting_confirm'
    t(client, 'confirm')
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'
    assert fake.count('capture') == 1


def test_decline_voids(client, fake):
    _, link = to_approval(client)
    assert 'Declined' in client.post(link + '/decline').text
    assert fake.count('void') == 1
    r = t(client, 'confirm')
    assert 'Alex declined' in r['say'] and r['state'] == 'voided' and fake.count('capture') == 0


def test_under_threshold_needs_no_approval(client, fake):
    setup(client); contact(client, threshold='90.00')
    t(client, 'hoodie'); t(client, 'add it in medium')
    assert t(client, 'check out')['state'] == 'awaiting_confirm'
