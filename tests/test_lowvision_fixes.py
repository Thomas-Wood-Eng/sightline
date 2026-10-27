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
