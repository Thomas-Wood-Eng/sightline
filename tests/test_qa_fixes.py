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
