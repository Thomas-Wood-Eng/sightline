# Sightline

A voice- and keyboard-first shopping agent for blind and low-vision people, built for the PayPal AI Hackathon.
PayPal holds the money, Sightline reads back PayPal's own numbers, and nothing is paid until you say "confirm" and type your PIN.

## Run locally

1. Python 3.13 with `pip install fastapi uvicorn itsdangerous rank_bm25 httpx pytest`.
2. Copy `.env.example` to `.env` and fill in the PayPal sandbox `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` and a random `SESSION_SECRET`.
3. Start the server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, then open http://127.0.0.1:8000.
4. Answer the Setup questions (screen reader yes/no, a 4-digit PIN, spending caps), then choose **Link PayPal** and log in as the
   sandbox **personal** buyer (the business account cannot approve).
   - Shortcut for local testing: set `DEMO_VAULT_ID` to an already-approved sandbox vault id to skip linking.
5. Try: "warm hoodie under 40", "describe number 1", "add it", "check out", "confirm", then type the PIN.

Tests: `python -m pytest tests` (PayPal is mocked). Live sandbox hold/capture/void:
`SIGHTLINE_LIVE=1 python -m pytest tests/test_live_sandbox.py` (needs `spike_state.json` with a `vault_id`).

Behind a proxy (e.g. Render), run uvicorn with `--proxy-headers` and set `HTTPS_ONLY=1` so the PayPal return URL and cookie are https.
