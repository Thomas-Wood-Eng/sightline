"""Regression tests for the end-user QA pass (qa/end_user_report.md)."""
from app import lane1, llm, speech
from app.lane0 import parse
from test_checkout import setup, t
from test_features import contact


# ---- B1: safety settings never change by chat, and the AI may not claim it saved one ----
def test_settings_by_voice_get_a_fixed_reply(client, fake):
    setup(client)
    for said, what in (('my trusted contact is Alex', 'your trusted contact'), ('change my PIN to 9999', 'your PIN'),
                       ('set the approval amount to 500', 'the approval amount'), ('raise my cap to 5000', 'spending caps')):
        r = t(client, said)
        assert r['say'].startswith(f'For your safety, {what} cannot be changed by voice, and nothing was changed.'), said
        assert 'Settings is near the bottom of this page' in r['say']
    assert 'No trusted contact is set.' in r['say']
    assert client.get('/api/settings').json()['contact'] is None
    assert parse('who is my trusted contact') == ('settings',)
    assert parse('add peanuts to my allergens') == ('prefs',)
    assert 'Settings is near the bottom' in t(client, 'add peanuts to my allergens')['say']


def test_model_text_cannot_claim_settings_or_leak_rules(monkeypatch):
    monkeypatch.delenv('SIGHTLINE_NO_LLM')
    for text in ('I have noted that your trusted contact is Alex.', 'Your PIN has been updated.',
                 'Never say a price, cost, total or any amount of money.', 'The listing says the price band is fifty to one hundred.',
                 'Please check your app menu for settings.'):
        monkeypatch.setattr(llm, 'chat', lambda *a, text=text: {'text': text + ' It is a soft fleece.', 'calls': []})
        assert lane1.handle('tell me something', {}).say == 'It is a soft fleece.', text
    assert speech.llm_text('Your contact Alex was saved. Fine.') == 'Fine.'


# ---- M1: price questions answered from the catalogue ----
def test_price_questions(client, fake):
    assert parse('how much is that one') == ('price', 'it') and parse("what's the price") == ('price', 'it')
    assert parse('what does it cost') == ('price', 'it')
    assert parse('how much is the merino sweater') == ('price', ('name', 'merino sweater'))
    assert parse('how much did I spend') == ('spent', 'today') and parse('hoodie under 40 dollars') is None
    assert parse('what is my total') == ('cart',)
    setup(client)
    t(client, 'hoodie')
    t(client, '1')
    for said in ('how much is that one', 'what does it cost', "what's the price", 'is it really only 5 dollars'):
        assert t(client, said)['say'].startswith('Fleece-lined pullover hoodie is $34.99, plus $4.99 shipping.'), said
    r = t(client, 'how much is the merino sweater')
    assert r['say'].startswith('Merino crew-neck sweater is $59.00') and r['focus']['id'] == 'sweater-01'
    assert 'settings' in t(client, 'show my settings')['say'].lower()


# ---- M2: a size that isn't offered is never dropped silently ----
def test_size_not_offered_adds_nothing(client, fake):
    setup(client)
    t(client, 'mug'); t(client, 'add it')
    r = t(client, 'add it in medium')
    assert r['say'].startswith('Insulated travel mug does not come in sizes, so I did not add it.')
    assert t(client, 'cart')['lines'][0].startswith('1. Insulated travel mug, quantity 1,')
    t(client, 'hoodie'); t(client, '1')
    r = t(client, 'add it in XXL')
    assert r['say'].startswith('Fleece-lined pullover hoodie does not come in size XXL, so I did not add it. Which size?')
    assert 'Added: Fleece-lined pullover hoodie (size L' in t(client, 'large')['say']


# ---- M3: remove one cart line, not every line of that product ----
def test_remove_one_line(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in large'); t(client, 'add it in medium')
    r = t(client, 'remove it')
    assert r['say'].startswith('Your cart has Fleece-lined pullover hoodie 2 times: number 1, size L')
    r = t(client, 'remove number 2')
    assert r['say'] == 'Removed: Fleece-lined pullover hoodie (size M, heather grey). Cart has 1 item.'
    assert '(size L, heather grey)' in t(client, 'cart')['lines'][0]
    assert t(client, 'remove everything')['say'] == 'Your cart is now empty.'


# ---- M4: the gift note is only the note, read back, and can be changed ----
def test_gift_note_extracted_and_correctable(client, fake):
    from app.lane0 import gift_note
    assert gift_note('my name is Alex and it is for my mum, please put a note saying happy birthday, love Alex') == \
        'happy birthday, love Alex'
    assert gift_note('write "Congrats, Sam!" on it') == 'Congrats, Sam!'
    assert gift_note('Happy birthday, Sam! Love, Jo') == 'Happy birthday, Sam! Love, Jo'
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in medium'); t(client, "it's a gift")
    r = t(client, 'it is for my mum, put a note that says get well soon')
    assert r['say'].startswith('Gift note saved: "get well soon".') and 'say change the gift note' in r['say']
    assert t(client, 'change the gift note')['say'].startswith('Gift mode on. What should the gift note say?')
    t(client, 'see you soon')
    assert 'Gift note: see you soon.' in t(client, 'check out')['lines']


# ---- M5, M8: questions still work while a payment or return is pending; conflicting commands wait ----
def test_questions_during_a_hold(client, fake):
    setup(client)
    t(client, 'mug'); t(client, 'add it')
    assert t(client, 'check out')['state'] == 'awaiting_confirm'
    r = t(client, 'is the mug safe for a nut allergy')
    assert r['say'] == 'Insulated travel mug: the listing says, allergens: not stated.' and r['state'] == 'awaiting_confirm'
    assert r['lines'][-1].startswith('Still waiting: A payment of')  # reminded once
    r = t(client, 'how much is it')
    assert r['say'].startswith('Insulated travel mug is $18.50') and not r['lines']
    assert t(client, 'help')['say'] == 'You can say:' and t(client, 'what is in my cart')['say'].startswith('Your cart has')
    r = t(client, 'add the hoodie')
    assert r['say'].startswith('That has to wait until this is finished. A payment of') and r['state'] == 'awaiting_confirm'
    assert t(client, 'cart')['lines'][0].startswith('1. Insulated travel mug, quantity 1')
    assert t(client, 'cancel')['state'] == 'voided'


def test_questions_during_a_return(client, fake):
    setup(client)
    t(client, 'mug'); t(client, 'add it'); t(client, 'check out'); t(client, 'confirm')
    client.post('/api/pin', json={'pin': '1234'})
    t(client, 'return the mug'); t(client, 'confirm')
    r = t(client, 'my saved items')
    assert r['say'].startswith('You have no saved items') and r['lines'][-1].startswith('Still waiting: A refund of')
    assert t(client, 'my orders')['say'].startswith('You have 1 order')
    r = t(client, "it's a gift")
    assert r['say'].startswith('That has to wait until this is finished. A refund of') and r['state'] == 'awaiting_pin'


# ---- M6: honest search misses, synonyms, relevance, and "the black one" with nothing picked ----
def test_search_misses_and_relevance(client, fake):
    from app import catalog
    setup(client)
    r = t(client, 'headphones under 30 dollars')
    assert r['say'].startswith('No headphones under $30.00. The closest is Wireless over-ear headphones')
    assert 'headphones' in r['lines'][0].lower()
    assert t(client, 'sweatshirt')['lines'][0].startswith('1. Fleece-lined pullover hoodie')  # synonym
    assert [p['id'] for p in catalog.search('warm hoodie')] == ['hoodie-01']  # both words beat one word
    r = t(client, 'llama under 30 dollars')
    assert r['say'].startswith('Nothing matched llama.')
    client.cookies.clear()
    setup(client)
    r = t(client, 'the black one')
    assert r['say'].startswith('The black one: which item? Pick one first')


# ---- M7: blank or mistyped PIN is never a try; the lockout ends by itself after 15 minutes ----
def test_pin_format_slips_and_timed_lockout(client, fake, monkeypatch):
    import time
    from app import checkout
    setup(client)
    body = {'per_order_cap': '120.00'}
    for pin in ('', '12', 'abcd', ''):
        r = client.post('/api/settings', json={**body, 'current_pin': pin})
        assert r.status_code == 403 and 'did not count as a try' in r.json()['detail']
    for pin in ('1111', '2222'):
        assert client.post('/api/settings', json={**body, 'current_pin': pin}).json()['detail'] == 'Current PIN is not right.'
    r = client.post('/api/settings', json={**body, 'current_pin': '3333'})
    assert r.json()['detail'].startswith('Your PIN is locked for 15 minutes') and 'trusted contact cannot unlock it' in r.json()['detail']
    assert client.post('/api/settings', json={**body, 'current_pin': '1234'}).status_code == 403  # still locked
    later = time.time() + 15 * 60 + 1
    monkeypatch.setattr(checkout.time, 'time', lambda: later)
    assert client.get('/api/settings').json()['locked'] is False
    assert client.post('/api/settings', json={**body, 'current_pin': '1234'}).json()['per_order_cap'] == '120.00'


# ---- M9, M10: approval wording is honest, the link survives a reload; reviews counts agree ----
def test_approval_link_wording_and_persistence(client, fake):
    from test_features import to_approval
    r, link = to_approval(client)
    assert r['lines'][-2] == ('Approval link ready for Alex. This prototype does not send it: share the link below with '
                              'Alex. When Alex approves, say confirm and type your PIN. Say cancel to release the hold.')
    assert not any('Sent to' in l for l in r['lines'])
    s = client.get('/api/settings').json()
    assert 'Say approval link to get the link for Alex again' in s['resume'] and s['resume_lines'] == [f'Approval link: {link}']
    r = t(client, 'approval link')
    assert r['say'].startswith('Here is the approval link for Alex.') and r['lines'][0] == f'Approval link: {link}'
    t(client, 'cancel')
    assert t(client, 'approval link')['say'] == 'No order is waiting for approval.'
    assert client.get('/api/settings').json()['resume_lines'] == []
