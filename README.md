# Sightline

A voice- and keyboard-first shopping agent for blind and low-vision people, built for the PayPal AI Hackathon.
PayPal holds the money, Sightline reads back PayPal's own numbers, and nothing is paid until you say "confirm" and type your PIN.

## Features

- Search, describe ("listing says" vs "photo suggests"), compare, cart, all by voice or keyboard; at most 3 results.
- Checkout: PayPal holds the money, Sightline reads back PayPal's own numbers (the Readback), then "confirm" + typed PIN.
- **Undo window:** after the PIN, capture waits 10 seconds; "undo" or Escape voids the hold.
- **Sizes and colours:** "add it in medium", "the black one"; never adds a sized item without a size.
- **Scam and dark-pattern guard:** subscriptions, pre-ticked add-ons (never added unless asked), unusual shipping and
  "only 2 left" pressure are called out in plain words, by fixed rules, not by the AI.
- **Trusted contact:** orders over a set amount need approval on a signed, single-use page (link shown, not emailed).
- **Review summaries:** "what do people say about it?" (fictional demo reviews, clearly labelled).
- **Orders:** "my orders", "where is my order", "how much did I spend this week", "return the hoodie" (refund behind
  the same Readback + PIN), "order my usual coffee again".
- **Wishlist and gift mode:** "save it for later", "move it to my cart"; "it's a gift" adds a gift note sent to PayPal.
- **Preferences (Settings only):** default size, allergens always avoided in food, brief/normal/detailed replies,
  large text, simple mode (one result at a time).
- Installable as a PWA. Spending caps, PIN, trusted contact and preferences change only in Settings, never by chat.

## Run locally

1. Python 3.13 with `pip install fastapi uvicorn itsdangerous rank_bm25 httpx pytest`.
2. Copy `.env.example` to `.env` and fill in the PayPal sandbox `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` and a random `SESSION_SECRET`.
3. Start the server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, then open http://127.0.0.1:8000.
4. Answer the Setup questions (screen reader yes/no, a 4-digit PIN, spending caps), then choose **Link PayPal** and log in as the
   sandbox **personal** buyer (the business account cannot approve).
   - Shortcut for local testing: set `DEMO_VAULT_ID` to an already-approved sandbox vault id to skip linking.
5. Try: "warm hoodie under 40", "describe number 1", "add it", "check out", "confirm", then type the PIN.

Orders are kept in SQLite at `SIGHTLINE_DB` (default `data/sightline.db`, git-ignored). Optional env:
`GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` (pinned defaults in `app/llm.py`), `LLM_PROVIDER=anthropic` to use Claude
(needs `pip install anthropic`), `SIGHTLINE_UNDO_SECONDS` (default 10).
Demo reviews are generated offline: `python catalog/make_reviews.py` (Gemini free tier, resumable).

Tests: `python -m pytest tests` (PayPal is mocked). Live sandbox hold/capture/void:
`SIGHTLINE_LIVE=1 python -m pytest tests/test_live_sandbox.py` (needs `spike_state.json` with a `vault_id`).

Behind a proxy (e.g. Render), run uvicorn with `--proxy-headers` and set `HTTPS_ONLY=1` so the PayPal return URL and cookie are https.
