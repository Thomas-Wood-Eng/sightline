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
    assert len(r['lines'][0].split()) <= 15 and 'stars' in r['lines'][0]  # brief keeps name, price, rating (research req. 3)
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
    r = client.post('/api/finalize').json()  # the cookie is only an id now, so this sees the voided state
    assert r['state'] == 'voided' and fake.count('capture') == 0


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
    r = t(client, 'is it approved yet')
    assert r['say'].startswith('Alex approved') and r['state'] == 'awaiting_confirm'
    t(client, 'confirm')
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'captured'
    assert fake.count('capture') == 1


def test_confirm_after_approval_goes_straight_to_pin(client, fake):
    _, link = to_approval(client)
    client.post(link + '/approve')
    r = t(client, 'confirm')
    assert r['say'].startswith('Alex approved') and r['state'] == 'awaiting_pin'
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] in ('captured', 'undo_window')


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


# ---- 5. scam and dark-pattern guard ----
def test_warnings_are_deterministic():
    from app import speech
    base = {'name': 'Thing', 'price': 24.99, 'shipping': 2.99}
    w = speech.warnings([({**base, 'id': 'a', 'subscription': 'month'}, 1, ''),
                         ({**base, 'id': 'b', 'urgency': 'Only 2 left in stock!'}, 1, ''),
                         ({**base, 'id': 'c', 'shipping': 18.99}, 1, '')])
    assert w[0] == 'Heads up: Thing is a subscription that renews every month until you cancel.'
    assert 'sales pressure' in w[1]
    assert 'shipping for Thing is 18.99 US dollars, unusually high for an item costing 24.99 US dollars' in w[2]
    assert speech.warnings([(base | {'id': 'd'}, 1, '')]) == []


def test_preticked_addon_never_added_unless_asked(client, fake):
    setup(client, order_cap='200.00')
    t(client, 'headphones'); t(client, 'add it')
    rb = ' '.join(t(client, 'check out')['lines'])
    assert 'pre-ticks a 2-year protection plan for 9.99 US dollars. I did not add it.' in rb
    items = next(iter(fake.seen.values()))['purchase_units'][0]['items']
    assert len(items) == 1
    t(client, 'cancel')
    assert 'Added: 2-year protection plan for' in t(client, 'add the protection plan')['say']
    rb = ' '.join(t(client, 'check out')['lines'])
    assert 'pre-ticks' not in rb and 'Item 2: 2-year protection plan' in rb and 'Unit price 9.99 US dollars' in rb


# ---- 6. review summaries ----
def test_parse_reviews():
    assert parse('what do people say about it') == ('reviews', 'it')
    assert parse('reviews for number 2') == ('reviews', ('n', 2))
    assert parse('is it any good') == ('reviews', 'it')
    assert parse('read the reviews') == ('reviews', 'it')


def test_review_summary_numbers_from_data():
    from app import speech
    p = {'name': 'Mug'}
    data = {'reviews': [{'stars': 5, 'text': 'x'}, {'stars': 4, 'text': 'y'}, {'stars': 2, 'text': 'z'}],
            'summary': {'pros': ['keeps tea hot', 'lasts 10 years'], 'cons': ['heavy', 'costs $5 too much'],
                        'complaint': 'lid leaks'}}
    say, lines = speech.reviews(p, data)
    assert say == 'Reviews say, from 3 demo reviews averaging 3.7 stars:'
    assert lines == ['People like: keeps tea hot.', 'Downsides: heavy.', 'Most repeated complaint: lid leaks.']
    assert speech.reviews(p, None)[0] == 'There are no reviews for Mug yet.'


def test_reviews_file_is_labelled_and_consistent():
    import json
    from app import catalog
    if not catalog.REVIEWS:
        return
    ratings = {p['id']: p['rating'] for p in json.loads((catalog.DIR / 'catalog.json').read_text(encoding='utf-8'))}
    assert 'not from real customers' in catalog.REVIEWS['_about']
    for pid, r in catalog.REVIEWS.items():
        if pid == '_about':
            continue
        assert 5 <= len(r['reviews']) <= 12
        stars = [x['stars'] for x in r['reviews']]
        assert abs(sum(stars) / len(stars) - ratings[pid]) <= 0.5 / len(stars) + 1e-9


# ---- 7. order history, tracking, spending ----
def buy(client, what='hoodie', add='add it in medium'):
    t(client, what); t(client, add); t(client, 'check out'); t(client, 'confirm')
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['state'] == 'captured', r
    return r


def test_parse_ledger_commands():
    assert parse("where's my order") == ('track', '')
    assert parse('where is my hoodie order') == ('track', 'hoodie')
    assert parse('my orders') == ('orders',) and parse('order history') == ('orders',)
    assert parse('how much did I spend this week') == ('spent', 'week')
    assert parse('how much have I spent today') == ('spent', 'today')
    assert parse('place my order') == ('checkout',)


def test_orders_tracking_spending(client, fake):
    setup(client)
    assert t(client, 'my orders')['say'] == 'You have no orders yet.'
    buy(client)
    buy(client, 'mug', 'add it')
    r = t(client, 'my orders')
    assert r['say'] == 'You have 2 orders.' and 'Insulated travel mug' in r['lines'][0]
    assert 'Paid 41.73 US dollars.' in r['lines'][1]
    r = t(client, 'where is my hoodie order')
    assert 'PayPal shows it as completed' in r['say'] and 'Estimated delivery' in r['say']
    # 41.73 + (18.50 + 3.99 + 0.93 = 23.42) = 65.15, all from the ledger
    assert t(client, 'how much did I spend this week')['say'] == \
        'This week, since Monday, you spent 65.15 US dollars on 2 orders, after refunds.'
    assert client.get('/api/settings').json()['spent_today'] == '65.15'


# ---- 8. returns and refunds ----
def test_return_one_line_with_readback_confirm_pin(client, fake):
    setup(client, order_cap='200.00')
    t(client, 'hoodie'); t(client, 'add it in medium'); t(client, 'mug'); t(client, 'add it')
    t(client, 'check out'); t(client, 'confirm'); client.post('/api/pin', json={'pin': '1234'})
    assert parse('return the hoodie') == ('return', 'the hoodie')
    r = t(client, 'return the hoodie')
    text = ' '.join(r['lines'])
    # hoodie 34.99 + its 5% tax 1.75 = 36.74; shipping kept
    assert 'Return: Fleece-lined pullover hoodie (size M, heather grey). Quantity 1.' in text
    assert 'Refund: 36.74 US dollars.' in text and 'Shipping is not refunded' in text
    assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'awaiting_confirm'  # no PIN before confirm
    assert fake.count('refund') == 0
    assert t(client, 'confirm')['state'] == 'awaiting_pin'
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['say'].startswith('Refunded 36.74 US dollars to your PayPal.') and fake.count('refund') == 1
    assert 'not already refunded' in t(client, 'return the hoodie')['say']  # one refund per line
    assert '36.74 US dollars refunded' in ' '.join(t(client, 'my orders')['lines'])
    assert 'Return cancelled' in (t(client, 'return the mug'), t(client, 'cancel'))[1]['say']
    assert fake.count('refund') == 1


# ---- 9. reorder ----
def test_parse_reorder():
    assert parse('order my usual coffee again') == ('reorder', 'coffee')
    assert parse('reorder the last thing') == ('reorder', '')
    assert parse('buy it again') == ('reorder', '')


def test_reorder_starts_checkout(client, fake):
    setup(client)
    assert 'could not find' in t(client, 'reorder the last thing')['say']
    buy(client)
    buy(client, 'mug', 'add it')
    buy(client, 'mug', 'add it')
    r = t(client, 'order my usual mug again')
    assert r['say'].startswith('Added again: Insulated travel mug.') and r['state'] == 'awaiting_confirm'
    t(client, 'cancel'); t(client, 'clear the cart')
    r = t(client, 'reorder the last thing')
    assert r['state'] == 'awaiting_confirm' and 'Item 1: Insulated travel mug.' in ' '.join(r['lines'])
    t(client, 'cancel'); t(client, 'clear the cart')
    r = t(client, 'order my usual hoodie again')
    assert 'Item 1: Fleece-lined pullover hoodie (size M, heather grey).' in ' '.join(r['lines'])


# ---- 10. wishlist ----
def test_parse_wishlist():
    assert parse('save it for later') == ('save', 'it')
    assert parse('add number 2 to my wishlist') == ('save', ('n', 2))
    assert parse('my saved items') == ('wishlist',) and parse('show my wish list') == ('wishlist',)
    assert parse('move it to my cart') == ('move', 'it') and parse('move number 1 to the cart') == ('move', ('n', 1))


def test_wishlist_flow(client, fake):
    setup(client)
    assert 'no saved items' in t(client, 'my saved items')['say']
    t(client, 'hoodie'); t(client, 'add it in large')
    r = t(client, 'save it for later')
    assert r['say'].startswith('Saved for later: Fleece-lined pullover hoodie (size L, heather grey). Moved out of your cart.')
    assert t(client, 'cart')['say'] == 'Your cart is empty.'
    t(client, 'mug'); t(client, 'save it')
    r = t(client, 'my saved items')
    assert r['say'].startswith('You have 2 saved items') and r['lines'][1] == '2. Insulated travel mug, $18.50.'
    assert '(size L, heather grey)' in t(client, 'move number 1 to my cart')['say']
    assert len(t(client, 'my saved items')['lines']) == 1


# ---- 11. gift mode ----
def test_gift_note_sent_to_paypal_and_read_back(client, fake):
    setup(client)
    assert parse("it's a gift") == ('gift',) and parse('not a gift') == ('gift_off',)
    t(client, 'mug'); t(client, 'add it')
    assert 'What should the gift note say' in t(client, "it's a gift")['say']
    assert t(client, 'Happy birthday, Sam! Love, Jo')['say'].startswith('Gift note saved: Happy birthday, Sam! Love, Jo.')
    rb = t(client, 'check out')['lines']
    assert 'Gift note: Happy birthday, Sam! Love, Jo.' in rb
    assert next(iter(fake.seen.values()))['purchase_units'][0]['description'] == 'Gift note: Happy birthday, Sam! Love, Jo'
    t(client, 'confirm'); client.post('/api/pin', json={'pin': '1234'})
    t(client, 'mug'); t(client, 'add it')
    assert not any('Gift' in l for l in t(client, 'check out')['lines'])  # gift mode ends with the order


def test_gift_without_note(client, fake):
    setup(client)
    t(client, 'mug'); t(client, 'add it'); t(client, 'this is a gift')
    assert 'no note' in t(client, 'no note')['say']
    assert 'This is a gift, with no note.' in t(client, 'check out')['lines']


# ---- 12. PWA ----
def test_pwa_files(client):
    import json
    m = json.loads(client.get('/static/manifest.webmanifest').text)
    assert m['display'] == 'standalone' and {i['sizes'] for i in m['icons']} == {'192x192', '512x512'}
    assert client.get('/static/icon-512.png').status_code == 200
    sw = client.get('/sw.js')
    assert sw.status_code == 200 and 'javascript' in sw.headers['content-type'] and '/api' in sw.text
    assert 'manifest.webmanifest' in client.get('/').text


# ---- 13. engineering: pinned models, optional Claude path ----
def test_llm_models_pinned_and_claude_path(monkeypatch):
    import sys, types as T
    from app import llm
    assert 'latest' not in llm.PRIMARY and 'latest' not in llm.FALLBACK
    monkeypatch.setattr(llm, 'PROVIDER', 'anthropic')
    monkeypatch.setitem(sys.modules, 'anthropic', None)  # not installed -> no-AI fallback, never Gemini
    assert llm.chat('sys', 'hi', []) is None
    blk = lambda **k: T.SimpleNamespace(**k)
    seen = {}

    class Client:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            seen.update(kw)
            return blk(stop_reason='tool_use', content=[blk(type='text', text='Looking.'),
                                                        blk(type='tool_use', name='search_products', input={'query': 'mug'})])
    fake = T.SimpleNamespace(Anthropic=Client, APIError=Exception)
    monkeypatch.setitem(sys.modules, 'anthropic', fake)
    tool = {'name': 'search_products', 'description': 'd', 'parameters': {'type': 'object'}}
    out = llm.chat('sys', 'a mug', [tool])
    assert out['calls'] == [('search_products', {'query': 'mug'})] and out['text'] == 'Looking.'
    assert seen['tools'][0]['input_schema'] == {'type': 'object'}
