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
