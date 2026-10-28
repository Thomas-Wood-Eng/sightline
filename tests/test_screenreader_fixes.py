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
