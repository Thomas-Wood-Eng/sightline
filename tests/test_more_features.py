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
