# Sightline

A voice- and keyboard-first shopping agent for blind and low-vision people, built for the PayPal AI Hackathon.
PayPal holds the money, Sightline reads back PayPal's own numbers, and nothing is paid until you say "confirm" and type your PIN.

## For judges

- **Live app:** _link added after deploy_ · **Demo video:** _link added after upload_
- **Try it instantly:** the live app has a pre-linked PayPal **sandbox** wallet (fake money). Answer the Setup questions
  (any 4-digit PIN), then type or say: "find me a warm hoodie", "tell me about the first one", "add it", "medium",
  "check out", "confirm", and type your PIN.
- **Link your own sandbox account instead:** choose **Link PayPal** and log in with a PayPal sandbox **personal** (buyer)
  account. A **business** account is the seller and PayPal will refuse it ("you are logging into the account of the seller").
  Sandbox test-buyer credentials are in the Devpost testing instructions.
- **Things worth trying:** a nut allergy ("a snack for my kid, she has a nut allergy"), "what do people say about it",
  headphones (a pre-ticked protection plan is called out and not added), "undo" within 10 seconds of the PIN,
  a trusted contact in Settings (orders above the amount need their approval), "return the hoodie".
- Works with NVDA, JAWS, VoiceOver or no screen reader; voice input needs Chrome or Edge, typing works everywhere.

## How it uses PayPal and AI

- **PayPal (sandbox, REST, called only by our code, never by the AI):** the buyer saves PayPal once (Vault v3 setup token →
  full-page PayPal login → payment token). Each purchase is an Orders v2 `AUTHORIZE` with that `vault_id`: PayPal holds the
  money, Sightline reads back PayPal's own `amount.breakdown`, then captures on confirm + PIN or voids on cancel/undo.
  Every checkout attempt has one `PayPal-Request-Id`, so a repeated "confirm" can never charge twice. Refunds use
  `/v2/payments/captures/{id}/refund` behind the same Readback + PIN.
- **AI (Gemini, free tier):** offline, Gemini with vision writes accessible product descriptions from the photos
  ("listing says" vs "photo suggests", reviewed by hand). Live, a fast Gemini model handles free-form requests with tools,
  but never sees a price and its text passes a money filter: every amount you hear is rendered from catalogue or PayPal data.
  Fixed commands and the whole checkout run without any AI. **The AI suggests; it never holds the keys.**

## Features

- Search, describe ("listing says" vs "photo suggests"), compare, cart, all by voice or keyboard; at most 3 results.
- Checkout: PayPal holds the money, Sightline reads back PayPal's own numbers (the Readback), then "confirm" + typed PIN.
- **Undo window:** after the PIN, capture waits 10 seconds; "undo" or Escape voids the hold.
- **Sizes and colours:** "add it in medium", "the black one"; never adds a sized item without a size.
- **Scam and dark-pattern guard:** subscriptions, pre-ticked add-ons (never added unless asked), unusual shipping and
  "only 2 left" pressure are called out in plain words, by fixed rules, not by the AI.
- **Trusted contact:** orders over a set amount need approval on a signed, single-use page (link shown, not emailed).
  Their decision is said as soon as they make it, without the shopper asking.
- **Gift-card scam guard:** gift-card requests and scam pressure ("the IRS told me to", "keep it secret", "my grandson
  needs bail") get a calm warning, by fixed rules; gift card orders and any order after a warning need the trusted
  contact, who is told why. That is the shopper's choice in Settings ("If Sightline suspects a scam, ask my trusted
  contact before paying", off by default, PIN to change); turned off, the warning stays and the order takes the usual
  Readback + confirm + PIN. The contact sees the shopper's own words only with it on. No contact, no gift card checkout.
- **"Is this my package?":** photograph the delivery (or say "check my package"); Gemini vision compares it with the
  order and Sightline says "photo suggests this matches" or "may not match", then offers a return. Photo not kept.
- **Pay in 4, read aloud:** in range, the Readback adds "PayPal Pay in 4 may be available: 4 payments of X"; "pay later"
  explains it. Never chosen for you; in this prototype Sightline pays in full and Pay Later is chosen on PayPal's page.
- **Dispute help:** "I never got my order", "it arrived broken", "this isn't what I ordered" explain PayPal Purchase
  Protection, then offer the refund (same Readback + PIN).
- **Review summaries:** "what do people say about it?" (fictional demo reviews, clearly labelled).
- **Compare:** "compare those two", "compare 1 and 3", "which is better": only what differs, from catalogue data.
- **Orders:** "my orders", "where is my order", "how much did I spend this week", "what did I buy last month",
  "show my PayPal purchases" (from the order ledger, never the AI), "return the hoodie" (refund behind the same
  Readback + PIN), "order my usual coffee again".
- **Wishlist and gift mode:** "save it for later", "move it to my cart", "tell me if it gets cheaper", "alert me under
  30 dollars" (said once when the price gets there); "it's a gift" adds a gift note sent to PayPal.
- **Preferences (Settings only):** default size, allergens always avoided in food, brief/normal/detailed replies,
  large text, simple mode (one result at a time).
- Installable as a PWA. Spending caps, PIN, trusted contact and preferences change only in Settings, never by chat.

## Run locally

1. Python 3.13 with `pip install -r requirements.txt` (and `pytest` for the tests).
2. Copy `.env.example` to `.env` and fill in the PayPal sandbox `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`, a free `GEMINI_API_KEY` (Google AI Studio) and a random `SESSION_SECRET`.
3. Start the server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, then open http://127.0.0.1:8000.
4. Answer the Setup questions (screen reader yes/no, a 4-digit PIN, spending caps), then choose **Link PayPal** and log in as the
   sandbox **personal** buyer (the business account cannot approve).
   - Shortcut for local testing: set `DEMO_VAULT_ID` to an already-approved sandbox vault id to skip linking.
5. Try: "warm hoodie under 40", "describe number 1", "add it", "check out", "confirm", then type the PIN.

Orders are kept in SQLite at `SIGHTLINE_DB` (default `data/sightline.db`, git-ignored). Optional env:
`GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` (pinned defaults in `app/llm.py`), `LLM_PROVIDER=anthropic` to use Claude
(needs `pip install anthropic`), `SIGHTLINE_UNDO_SECONDS` (default 10), `SIGHTLINE_DEMO=1` (demo only: enables
`POST /api/demo/price` with `{"id": "hoodie-01", "price": "29.99"}` to show a price-drop alert; off by default).
Demo reviews are generated offline: `python catalog/make_reviews.py` (Gemini free tier, resumable).

Tests: `python -m pytest tests` (PayPal is mocked). Live sandbox hold/capture/void:
`SIGHTLINE_LIVE=1 python -m pytest tests/test_live_sandbox.py` (needs `spike_state.json` with a `vault_id`).

Behind a proxy (e.g. Render), run uvicorn with `--proxy-headers` and set `HTTPS_ONLY=1` so the PayPal return URL and cookie are https.

## Licence

Code: MIT (see LICENSE). Product photos in `app/static/img` keep their own licences (CC0, public domain, or CC BY), listed with attribution in CREDITS.md.
