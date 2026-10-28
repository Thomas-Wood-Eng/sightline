"""Regression tests for the low-vision usability report (qa/low_vision_report.md)."""
import threading, time

from app import paypal
from test_checkout import setup, t


# ---- bug 1: a settings save during a slow capture must not be lost (qa/debug_race.py) ----
def test_settings_saved_during_slow_capture_are_kept(fake, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    real = fake.capture
    monkeypatch.setattr(paypal, 'capture', lambda a, r: (time.sleep(0.8), real(a, r))[1])
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '1')
    with TestClient(app) as client:  # one event loop, so the two requests really overlap
        setup(client)
        t(client, 'hoodie'); t(client, 'add it in medium'); t(client, 'check out'); t(client, 'confirm')
        assert client.post('/api/pin', json={'pin': '1234'}).json()['state'] == 'undo_window'
        time.sleep(1.1)
        done = []
        fin = threading.Thread(target=lambda: done.append(client.post('/api/finalize').json()))
        fin.start(); time.sleep(0.3)  # the capture is now in flight
        body = {'contact_name': 'Alex', 'contact_email': 'alex@example.com', 'approval_threshold': '20', 'current_pin': '1234'}
        assert client.post('/api/settings', json=body).json()['contact']['name'] == 'Alex'
        fin.join()
        assert done[0]['state'] == 'captured'
        assert client.get('/api/settings').json()['contact']['name'] == 'Alex'
        t(client, 'hoodie'); t(client, 'add it in medium')
        assert t(client, 'check out')['state'] == 'awaiting_approval'


def test_session_survives_restart_via_sqlite(client, fake):
    from app import db
    setup(client)
    key = client.cookies['session']
    assert key.count('.') == 2 and 'pin' not in key  # the cookie is a signed id only, no state
    assert len(client.cookies['session']) < 120
    rows = db._conn().execute('SELECT data FROM sessions').fetchall()
    assert any('"pin"' in r['data'] for r in rows)
    assert client.get('/api/settings').json()['pin_set']


# ---- bug 3: the PIN box states the amount, from PayPal's order, not computed in the page ----
def test_reply_carries_payment_amount_text(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in medium')
    assert t(client, 'check out')['pay'] == 'Paying 41.73 US dollars to Sightline Demo Store'
    assert t(client, 'confirm')['pay'] == 'Paying 41.73 US dollars to Sightline Demo Store'
    assert client.get('/api/settings').json()['pay'] == 'Paying 41.73 US dollars to Sightline Demo Store'


# ---- bug 7: after a refund the session is clean; a stale "return waiting" never claims nothing was refunded ----
def to_return_pin(client):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in medium'); t(client, 'check out'); t(client, 'confirm')
    client.post('/api/pin', json={'pin': '1234'})
    t(client, 'return the hoodie'); t(client, 'confirm')


def test_refund_leaves_clean_state(client, fake):
    from app import db
    to_return_pin(client)
    key = client.cookies['session'].split('.')[0]
    stale = db.load_session(key)  # as the old cookie was if the reply never reached the page
    assert stale['co']['kind'] == 'refund' and stale['co']['state'] == 'awaiting_pin'
    r = client.post('/api/pin', json={'pin': '1234'}).json()
    assert r['say'].startswith('Refunded 36.74') and r['state'] == 'idle'
    assert db.load_session(key)['co'] == {'state': 'idle'}  # saved server-side, whatever happens to the reply
    assert t(client, 'cancel')['say'] == 'Nothing is on hold, so there is nothing to cancel.'
    # even a stale return step (say, a crash before the session was saved) is cleared from the ledger
    db.save_session(key, __import__('json').dumps(stale))
    assert client.get('/api/settings').json()['state'] == 'idle'
    r = t(client, 'cancel')
    assert 'Nothing was refunded' not in r['say'] and 'return is waiting' not in r['say']
    assert fake.count('refund') == 1


# ---- bug 9: a bare size is taken as a size, or answered with a clear prompt; nothing replaces the results ----
def test_bare_size(client, fake):
    from app.lane0 import bare_size
    assert [bare_size(x) for x in ('M', 'medium', 'size XL', 'xs', 'mug', 'add it')] == ['M', 'M', 'XL', 'XS', None, None]
    setup(client)
    t(client, 'find me something warm')  # two results, nothing picked yet
    assert t(client, 'M')['say'] == 'Size M for which item? Say the number first, for example: add number 1 in M.'
    assert t(client, 'tell me about the second one')['say'].startswith('Fleece-lined pullover hoodie')  # results kept
    assert t(client, 'M')['say'].startswith('Added: Fleece-lined pullover hoodie (size M')
    r = t(client, 'XXL')
    assert 'does not come in size XXL' in r['say'] and 'Which size?' in r['say']
    assert t(client, 'S')['say'].startswith('Added: Fleece-lined pullover hoodie (size S')


# ---- bugs 10 and 12: the lockout states the way back; the Settings PIN label names the trusted contact ----
def test_lockout_message_states_recovery(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it in medium'); t(client, 'check out'); t(client, 'confirm')
    for _ in range(3):
        r = client.post('/api/pin', json={'pin': '0000'}).json()
    assert 'say link PayPal' in r['say'] and '"Link PayPal again" link in the PayPal section' in r['say']
    assert 'Setup form asks you to choose a new PIN' in r['say'] and r['state'] == 'voided'


def test_settings_pin_label_names_trusted_contact(client):
    assert 'Current PIN, needed to change caps, PIN or trusted contact</label>' in client.get('/').text
