"""Regression tests for the screen-reader report (qa/screen_reader_report.md)."""
from test_checkout import setup, t, to_readback


def resume(client):
    return client.get('/api/settings').json()['resume']


# ---- issue 1: a reload mid-checkout says what is on hold, from server data, in every pending state ----
def test_reload_restores_pending_payment_in_every_state(client, fake, monkeypatch):
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '10')
    assert to_readback(client)['state'] == 'awaiting_confirm'
    r = resume(client)
    assert r.startswith('Welcome back. A payment of 41.73 US dollars is on hold for Fleece')
    assert r.endswith('Say repeat to hear the Readback, confirm to continue, or cancel to release it.')
    t(client, 'confirm')
    assert 'waiting for your PIN. Type it in the PIN box' in resume(client)
    rb = t(client, 'repeat')  # the Readback, not the last reply ("Confirmed. Now type your PIN")
    assert rb['say'].startswith('PayPal is holding the payment') and 'Total: 41.73 US dollars.' in rb['lines']
    client.post('/api/pin', json={'pin': '1234'})
    r = resume(client)
    assert 'PIN was accepted. PayPal takes the payment of 41.73 US dollars' in r and 'say undo' in r
    assert client.get('/api/settings').json()['due_in'] > 0  # the page restores the countdown
    t(client, 'undo')
    assert resume(client) is None


def test_reload_restores_approval_and_refund(client, fake):
    setup(client)
    client.post('/api/settings', json={'contact_name': 'Sam', 'contact_email': 's@example.com',
                                       'approval_threshold': '20', 'current_pin': '1234'})
    t(client, 'hoodie'); t(client, 'add number 1 in medium')
    assert t(client, 'check out')['state'] == 'awaiting_approval'
    assert 'waiting for Sam to approve' in resume(client)
    t(client, 'cancel')
    client.post('/api/settings', json={'contact_name': '', 'current_pin': '1234'})
    t(client, 'check out'); t(client, 'confirm'); client.post('/api/pin', json={'pin': '1234'})  # paid (undo 0 s)
    t(client, 'return the hoodie')
    assert resume(client).startswith('Welcome back. A refund of 36.74 US dollars for Fleece')  # shipping is not refunded


# ---- issue 2: a PIN-like message is never echoed, and the reply gives no hint whether it was the PIN ----
SAFE = "For your safety, numbers like a PIN are never shown or spoken."


def test_pin_like_message_refused_in_every_state(client, fake):
    setup(client)
    right, wrong = t(client, '1234'), t(client, '9999')  # idle
    assert right['say'] == wrong['say'] and right['say'].startswith(SAFE) and '1234' not in right['say']
    assert t(client, '12 34')['say'].startswith(SAFE) and t(client, '1-2-3-4')['say'].startswith(SAFE)
    client.post('/api/settings', json={'contact_name': 'Sam', 'contact_email': 's@example.com',
                                       'approval_threshold': '20', 'current_pin': '1234'})
    t(client, 'hoodie'); t(client, 'add number 1 in medium')
    assert t(client, 'check out')['state'] == 'awaiting_approval'
    r = t(client, '1234')
    assert r['say'].startswith(SAFE) and r['state'] == 'awaiting_approval'
    assert '1234' not in ' '.join(t(client, 'repeat')['lines'])


def test_short_numbers_still_work(client, fake):
    setup(client)
    t(client, 'hoodie')
    assert t(client, '1')['say'].startswith('Number 1:')  # a pick, not refused
    assert not t(client, '32')['say'].startswith(SAFE)


# ---- issue 3: a repeated "check out" while a hold exists places nothing and does not re-read the Readback ----
def test_repeated_checkout_is_idempotent_and_short(client, fake):
    to_readback(client)
    r = t(client, 'check out')
    assert r['say'].startswith('No new hold was placed. A payment of 41.73 US dollars is on hold for') and r['lines'] == []
    assert fake.count('hold') == 1 and r['state'] == 'awaiting_confirm'


# ---- issue 7: a settings save says only what changed, in 15 words or fewer ----
def test_settings_saved_names_only_changes(client, fake):
    setup(client)
    post = lambda **b: client.post('/api/settings', json=b)
    r = post(verbosity='detailed', per_order_cap='100.00', daily_cap='250.00').json()
    assert r['saved'] == 'Settings saved: detailed replies.'
    assert post(verbosity='detailed').json()['saved'] == 'Settings saved: nothing changed.'
    r = post(per_order_cap='120', current_pin='1234', default_size='M').json()['saved']
    assert r == 'Settings saved: default size M; per-order cap 120.00 US dollars.' and len(r.split()) <= 15
    r = post(output_mode='voice', verbosity='brief', simple_mode=True, large_text=True, default_size='L').json()['saved']
    assert len(r.split()) <= 15 and r.startswith('Settings saved: 5 changes.')


# ---- issue 11: a stray space in New PIN is "keep"; a bad new PIN names the field and burns no try ----
def test_new_pin_whitespace_and_error(client, fake):
    setup(client)
    r = client.post('/api/settings', json={'new_pin': ' ', 'verbosity': 'normal'})
    assert r.status_code == 200 and r.json()['saved'] == 'Settings saved: normal replies.'
    r = client.post('/api/settings', json={'new_pin': '12', 'current_pin': '1234'})
    assert r.status_code == 422 and r.json()['detail'].startswith('The new PIN must be exactly 4 digits.')
    r = client.post('/api/settings', json={'new_pin': '5678', 'current_pin': '1234'})
    assert r.json()['saved'] == 'Settings saved: new PIN set.'


# ---- issue 4: brief by default (research_ux.md), details on request ----
def test_brief_by_default_details_on_request(client, fake):
    setup(client)
    assert client.get('/api/settings').json()['prefs']['verbosity'] == 'brief'
    r = t(client, 'hoodie')
    assert all(len(l.split()) <= 15 and 'stars' in l for l in r['lines'])  # name, price and rating
    brief = t(client, 'tell me about the first one')
    words = lambda j: len(' '.join([j['say'], *j['lines']]).split())
    assert words(brief) <= 45 and brief['say'].count('.') <= 2  # the name and one sentence, then the price line
    for ask in ('more', 'tell me more', 'details', 'tell me more about it'):
        full = t(client, ask)
        assert words(full) > words(brief) and any(l.startswith('Listing says: size') for l in full['lines']), ask
    client.post('/api/settings', json={'verbosity': 'normal'})
    assert any(l.startswith('Common question') for l in t(client, 'details')['lines'])  # normal -> detailed


# ---- issue 6: "add it" after a search names the choices; with one result it just adds ----
def test_add_it_after_search(client, fake):
    setup(client)
    t(client, 'anything under 100')  # several results
    q = t(client, 'add it')['say']
    assert q.startswith('Which one: 1, ') and ', or 3, ' in q and q.endswith('?') and len(q.split()) <= 20, q
    t(client, 'travel mug')  # exactly one result, no sizes
    assert t(client, 'add it')['say'].startswith('Added: Insulated travel mug')
