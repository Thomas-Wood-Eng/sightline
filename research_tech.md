# Sightline: technical research (2026-10-27)

"Verify" marks claims I could not confirm in the docs. Those go into the day-1 spike.

## 1. PayPal vaulting (sandbox)
**Use Vault v3 "save without purchase", then Orders v2 with `vault_id`.** ([guide](https://developer.paypal.com/api/payment-tokens/save-without-purchase/paypal), [Vault v3 ref](https://developer.paypal.com/api/payment-tokens/v3/setup-tokens-create))
1. `POST https://api-m.sandbox.paypal.com/v3/vault/setup-tokens` with headers `PayPal-Request-Id` and `Authorization: Bearer`. Body:
   `payment_source.paypal{description, usage_pattern:"IMMEDIATE", usage_type:"MERCHANT", customer_type:"CONSUMER", permit_multiple_payment_tokens:false, experience_context{brand_name, locale, shipping_preference, return_url, cancel_url}}`.
   The response links include `approve`, for example `https://sandbox.paypal.com/agreements/approve?approval_session_id=…`. **A plain `window.location = approve` is a full-page redirect, so no popup and no SDK are needed.** The setup token expires after 3 days.
2. On `return_url`, call `POST /v3/vault/payment-tokens` with `{payment_source:{token:{id:<setup_token>, type:"SETUP_TOKEN"}}}`. This returns the payment-token `id` (the `vault_id`) and `customer.id`. Which query params come back on `return_url` is not documented: keep the setup-token id in the session instead of relying on them.
3. For each purchase, `POST /v2/checkout/orders` with `payment_source.paypal.vault_id`. With `intent:"CAPTURE"` the documented sample returns `status:"COMPLETED"` in one call, with no buyer present and no separate capture.
   - **Better for us: `intent:"AUTHORIZE"`.** The amount is held but not moved, and the readback uses PayPal's own numbers. Then `POST /v2/payments/authorizations/{id}/capture` on confirm, or `/void` on cancel ([authorize](https://docs.paypal.ai/reference/api/rest/orders/authorize-payment-for-order)). Verify that vault_id with AUTHORIZE completes without approval.
- **Optional flags:** `payment_source.paypal.stored_credential{payment_initiator: CUSTOMER|MERCHANT, usage: FIRST|SUBSEQUENT|DERIVED, usage_pattern}` ([definition](https://developer.paypal.com/api/orders/v2/definitions/paypal_wallet_stored_credential)). Our purchases are **CUSTOMER**-initiated, because the buyer is present by voice.
- **Alternative: save during purchase** (`payment_source.paypal.attributes.vault{store_in_vault:"ON_SUCCESS", usage_type:"MERCHANT"}` plus `experience_context.return_url/cancel_url`). The first order needs a redirect, and the vault id appears at `payment_source.paypal.attributes.vault.id` after capture with `status:"VAULTED"` ([guide](https://developer.paypal.com/docs/checkout/save-payment-methods/during-purchase/orders-api/paypal/)). Keep it as plan B, because it mixes "link" and "first purchase" into one step.
- **JS SDK:** the v6 SDK has `presentationMode: "redirect"` among `auto|popup|modal|redirect` ([v6 checkout](https://developer.paypal.com/docsai/payments/methods/paypal/sdk/js/v6/paypal-checkout)). We don't need it, because the server-driven `approve` redirect is simpler and keeps PayPal's pages fully native for the screen reader.
- **Enablement:** Sandbox App Settings → App Feature Options → **Accept payments** → Advanced options → confirm **Vault** is ticked. The docs don't say whether it is on by default, so check it. Errors such as `NOT_ENABLED_TO_VAULT_PAYMENT_SOURCE` or `PERMISSION_DENIED` usually mean it is off, or that sandbox and live hosts or credentials are mixed. No extra OAuth scope is set by hand; the client-credentials token carries the app's features.
- **Idempotency:** send `PayPal-Request-Id` (a UUID) on every create, capture and void. Generate it **once per checkout attempt** and store it, so a repeated "confirm" replays instead of charging twice.
- **Sandbox accounts:** the dashboard auto-creates a Personal buyer (`sb-…@personal.example.com`) and a Business merchant. Ship a dedicated buyer login in the README for judges.
- **Gotchas:**
  - The docs require Risk Data Acquisition (FraudNet `PayPal-Client-Metadata-Id`) for customer-initiated transactions with PayPal tokens; missing it risks declines in production. Add it if there is time; sandbox is likely lenient (verify).
  - "Reference transactions must be approved" applies to live accounts.
  - Vault IDs only appear after authorize or capture in the during-purchase flow.

## 2. Agent Toolkit / MCP vs direct REST
- The [Agent Toolkit](https://github.com/paypal/agent-toolkit) supports TypeScript and Python, with OpenAI Agents, LangChain, Vercel AI SDK and MCP. Its tools include:
  - **Orders:** `create_order`, `get_order`, `pay_order`, `create_refund`, `get_refund`
  - **Shipment:** `create/get/update_shipment_tracking`
  - **Catalog:** `create_product`, `list_products`, `show_product_details`
  - **Other:** invoices (20 tools), disputes, subscriptions, `list_transactions`
- **`create_order` takes `items` (with prices), `currencyCode`, `shippingCost`, `returnUrl` and `cancelUrl`, but no `payment_source` or `vault_id`** ([params.ts](https://github.com/paypal/agent-toolkit/blob/main/typescript/src/shared/parameters.ts)). It cannot do our flow, and it would let the model supply prices.
- **Decision:** money-moving calls are direct REST in our own code, and never model tools. Optionally expose the Toolkit's **read-only** `get_order`, `get_refund` and `get_shipment_tracking` (plus a refund behind the same PIN gate), so "built on PayPal's Agent Toolkit" is honest without giving the model the till.
- No accessibility-specific features were found in JS SDK v6. A full-page redirect avoids the iframe and modal problems listed in research_sightline.md.

## 3. Voice pipeline
| Option | Notes |
|---|---|
| **Web Speech `SpeechRecognition`** | Chrome and Edge (`webkitSpeechRecognition`). Chrome streams audio to Google. Chromium 139+ has an on-device `processLocally` mode ([MDN](https://developer.mozilla.org/docs/Web/API/SpeechRecognition/processLocally)). Safari has it prefixed; Firefox has no support. Free and zero setup. |
| Deepgram Nova-3 streaming | About $0.005–0.009 per minute ([pricing roundup](https://www.activepieces.com/blog/deepgram-pricing-2026-per-minute-rates-and-add-ons)). Works in every browser via WebSocket, but needs a server token proxy. |
| OpenAI gpt-realtime / Gemini Live | Speech-to-speech is lowest latency, but it puts a second LLM in the loop, costs about $0.30 or more per minute for the flagship ([roundup](https://www.forasoft.com/blog/article/openai-realtime-api-pricing)) and **speaks over the screen reader**. Reject it. |
| Claude | The Messages API has no audio in or out, so wrap it with STT/TTS. |

**Recommendation:**
- **Input:** push-to-talk with Web Speech on Chrome/Edge, with `processLocally=true` when `SpeechRecognition.available()` says so. On Firefox and Safari, or on error, fall back to the **always-present text box**.
  - Shortcut: shortcut: Deepgram fallback skipped; add it only if a tester needs Firefox.
- **Output:** the default is **screen-reader mode**. Each reply is appended to a `role="log"` / `aria-live="polite"` region, so NVDA, JAWS and VoiceOver speak it in the user's own voice and rate. "App voice" mode (for low-vision users without a screen reader) uses `speechSynthesis`. Never both: in app-voice mode, set the log to `aria-live="off"`.
- **Coexistence:**
  - PTT is a real `<button>`, because Space and Enter work in NVDA/JAWS browse mode, while single-letter shortcuts are swallowed. Add a modified hotkey such as Alt+Shift+M as a bonus.
  - Pressing PTT calls `speechSynthesis.cancel()`. A web page cannot silence the screen reader; the user presses Ctrl.
  - Recommend headphones, because the mic otherwise hears the screen reader.
  - Play a short earcon on start and stop, and an "on it" cue when a reply takes more than 1 second.

## 4. LLM agent layer
- **Models:**
  - **`claude-haiku-5-5`** is the chat loop ($0.10 / $0.50 per MTok). Set `output_config.effort:"low"`, because its default is medium.
  - **`claude-sonnet-5-5`** is the fallback if Haiku's tool choice is weak.
  - Opus 5.5 is too slow for voice turns, and its thinking cannot be disabled.
  - Forced `tool_choice` returns 400 on Sonnet/Opus 5.5: use `auto` plus `strict: true` on every tool.
  - Stream replies, and cache the system prompt and tools.
- **Tools (all `strict`, executed server-side):**
  - `search_products(query, max_price?, category?)`: filtering happens server-side.
  - `get_product_details(id)`
  - `describe_image(id)`: returns a **precomputed** Sonnet-vision description, generated once at seed time, human-reviewed and split into "listing says" and "photo suggests". That makes it instant and auditable.
  - `add_to_cart(id, qty)`, `remove_from_cart`, `read_cart()`
  - `start_checkout()`: creates the AUTHORIZE order and returns `{state:"awaiting_confirmation"}` only.
  - **`confirm_purchase` is NOT a model tool.** Confirm, PIN, cancel and repeat are handled by a deterministic server state machine that receives the raw utterance or keypad input before the LLM sees it.
- **The model never states prices.** The model returns structured output `{say: string, product_ids: [], action}`.
  - The server renders every price, total and rating line from a template (catalog for browsing, the PayPal order response `purchase_units[0].amount.breakdown` for checkout).
  - A guard rejects any `say` matching `/[$€£]|\d+(\.\d\d)?\s*(dollars?|cents?|bucks)|\bprice is\b/i`, then regenerates once or drops the text.
  - Tool results the model sees carry **no price fields**, only a `price_band` such as "under 50".
- **PIN:** a 4-digit keypad, typed by default, because speaking a PIN aloud leaks it. A spoken PIN is optional. Store it hashed (scrypt), with 3 tries then lockout. The spending cap is checked server-side before the order is created.

## 5. Catalog
- DummyJSON's code is MIT, but **the licence of its product photos is undocumented** ([repo](https://github.com/Ovi/DummyJSON)). That is a risk for a public repo and video.
- **Build a hand-made seed of about 40 products in `catalog.json`** (jackets, headphones, kitchen, groceries), with photos from Unsplash or Pexels (both licences allow free commercial use) and the photo URL plus credit stored per item.
- Groceries can come from Open Food Facts, whose images are CC BY-SA and need attribution in `CREDITS.md`.
- Invent the prices and store them only in the JSON.

## 6. Hosting
- **One FastAPI service on Render** (Python matches the user's skills) serving static HTML and vanilla JS. There is no SPA, so focus management stays simple and semantic.
  - Libraries: `httpx` for PayPal, `anthropic` for Claude.
  - Free tier: the service sleeps after 15 minutes idle with about a 1-minute cold start, and gets 750 hours a month ([Render free](https://render.com/docs/free)). Use the sponsor credits or the $7 Starter plan through Dec 15. Otherwise, add "first load may take a minute" to the README.
- **No database:** Render free Postgres expires (verify the 30-day expiry) and its disk is ephemeral. Keep the cart, PIN hash, cap, setup-token id, `vault_id` and `customer.id` in a signed httpOnly session cookie (Starlette `SessionMiddleware`). PayPal itself remains the record via `GET /v3/vault/payment-tokens?customer_id=`.
  - Shortcut: cookie state is lost if the cookie is cleared, which is acceptable for sandbox. Upgrade to Postgres if this goes real.
- **Secrets:** `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `ANTHROPIC_API_KEY` and `SESSION_SECRET` go in Render env vars, and `.env.example` goes in the repo.
- **Judges:** publish the sandbox buyer login, demo PIN 1234 and a $100 cap. Rate-limit the Claude calls per session.

## 7. Sponsors
- **Render** is the only natural fit: we host on it anyway.
- AG Grid and Bryntum are visual grid and scheduler widgets, a poor fit for a voice-first interface, and they add screen-reader risk. Skip them.
- APIMatic: PayPal's `paypal-server-sdk` is APIMatic-generated. If the APIMatic prize requires its SDKs, using that SDK instead of `httpx` could qualify. The prize terms could not be fetched (Devpost returned 403); check them.

## Recommended architecture
```
Browser (static HTML, role=log, PTT button, text box, PIN keypad)
  └─ POST /api/turn {text}  ──► FastAPI
        ├─ confirm/PIN/cancel state machine (no LLM)
        ├─ Claude Haiku 5.5 tool loop → catalog.json tools
        └─ templated renderer (all numbers) → {say, lines[]}
  GET  /link/start   → POST /v3/vault/setup-tokens → 302 to approve
  GET  /link/return  → POST /v3/vault/payment-tokens → session.vault_id
  POST /api/checkout → POST /v2/checkout/orders {intent:AUTHORIZE, vault_id}
                       → readback from response breakdown
  POST /api/confirm {pin} → POST /v2/payments/authorizations/{id}/capture
  POST /api/cancel        → .../void
```

## Ranked risks and mitigations
1. **vault_id order needs approval, or vault is not enabled.** Mitigation: the day-1 spike, the dashboard toggle, and plan B (save-during-purchase redirect, or a normal redirect per order).
2. **AUTHORIZE with vault_id is unsupported.** Mitigation: use CAPTURE, with the readback built from a server-computed breakdown that the PayPal response then confirms.
3. **Speaking over the screen reader, or unreliable Web Speech.** Mitigation: aria-live default mode, text fallback, and an NVDA test on day 2 rather than day 5.
4. **The LLM leaks a price.** Mitigation: no price fields in tool results, the regex guard, and templated lines.
5. **Cold start during judging.** Mitigation: a paid instance or credits through Dec 15.
6. **Image licence.** Mitigation: Unsplash/Pexels/OFF photos with `CREDITS.md`.

## Day-1 spike checklist
- [ ] Sandbox app: tick Vault; note the buyer and merchant logins.
- [ ] curl the setup token, approve in a browser, then create the payment token and record `vault_id`.
- [ ] curl an order with `vault_id`, once with CAPTURE and once with AUTHORIZE; confirm COMPLETED with no approval, then capture and void.
- [ ] Resend the same `PayPal-Request-Id` and confirm there is no double charge.
- [ ] Web Speech PTT on Chrome with NVDA running: check `processLocally`, and check that the aria-live log is spoken.
- [ ] Deploy a FastAPI hello-world to Render with env vars.
- [ ] Haiku 5.5 strict tool call round trip, timed.
