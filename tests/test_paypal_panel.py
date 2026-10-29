"""The page's PayPal panel: linked status and the order's steps at PayPal, all from server data."""
from test_checkout import setup, t


def steps(view):
    o = view['paypal']['order']
    return [(s['label'], s['state']) for s in o['steps']], o


def test_panel_follows_hold_pin_undo_capture_refund(client, fake, monkeypatch):
    setup(client)
    v = client.get('/api/settings').json()['paypal']
    assert v == {'linked': True, 'account': 'sandbox buyer account', 'order': None}
    t(client, 'hoodie'); t(client, 'add it in medium')
    st, o = steps(t(client, 'check out'))
    assert o['id'] == 'ORDER1' and o['amount'] == '41.73 US dollars' and not o['ended']
    assert st[:3] == [('PayPal linked', 'done'), ('On hold by PayPal', 'done'), ('You confirm with your Sightline PIN', 'current')]
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '10')
    t(client, 'confirm')
    st, o = steps(client.post('/api/pin', json={'pin': '1234'}).json())
    assert ('Undo window', 'current') in st and o['status'].startswith('PIN accepted')
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '0')
    st, o = steps(t(client, 'undo'))
    assert st[-1] == ('Released by PayPal', 'current') and o['ended'] and 'Nothing was charged' in o['status']
    t(client, 'check out'); t(client, 'confirm')
    st, o = steps(client.post('/api/pin', json={'pin': '1234'}).json())
    assert o['id'] == 'ORDER2' and all(s == 'done' for _, s in st) and o['status'] == 'PayPal captured 41.73 US dollars.'
    assert steps(t(client, 'hoodie'))[1]['id'] == 'ORDER2'  # the last order stays in the panel
    t(client, 'return the hoodie'); t(client, 'confirm')
    st, o = steps(client.post('/api/pin', json={'pin': '1234'}).json())
    assert o['kind'] == 'refund' and st[-1] == ('Refunded by PayPal', 'done') and o['amount'] == '36.74 US dollars'


def test_panel_shows_trusted_contact_step(client, fake):
    setup(client)
    client.post('/api/settings', json={'contact_name': 'Alex', 'contact_email': 'alex@example.com',
                                       'approval_threshold': '20', 'current_pin': '1234'})
    t(client, 'hoodie'); t(client, 'add it in medium')
    st, o = steps(t(client, 'check out'))
    assert ('Trusted contact approves', 'current') in st and 'trusted contact' in o['status']
