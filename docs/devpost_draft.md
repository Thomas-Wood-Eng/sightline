# Sightline: Devpost write-up (draft for review)

**Tagline:** Shop by voice or keyboard. Hear every dollar before it moves.

## Inspiration
Blind and low-vision shoppers can often *find* a product online, then lose it at checkout: CAPTCHAs, pop-ups, unlabelled
buttons and payment iframes a screen reader can't get into. CAPTCHA is the #1 barrier named by 1,539 screen-reader users in
WebAIM's survey, at least 2.2 billion people live with a vision impairment (WHO), and about 5,000 US accessibility lawsuits were
filed in 2025, roughly 70% against online stores (UsableNet). AI agents can now click through websites for people, but an agent
that moves money on your behalf has to be *trustworthy*, not just capable. We wanted the agent to do the clicking while the
person makes every decision.

## What it does
Sightline is a voice- and keyboard-first shopping assistant built on PayPal.
- **Find and understand products:** at most three results at a time, spoken briefly; descriptions separate what the
  *listing says* from what the *photo suggests*, and say "not stated" instead of guessing. Review summaries, comparisons,
  sizes and colours.
- **The Readback:** at checkout PayPal holds the money and Sightline reads back **PayPal's own numbers**: item, size,
  price, shipping, tax, total, delivery date, seller. Nothing is paid until the shopper says "confirm" and types their PIN.
- **Safety by code, not by prompt:** the AI never sees prices and can't move money; spending limits and the PIN change only
  in Settings; allergies are a hard filter; pre-ticked add-ons, subscriptions and "only 2 left" pressure are called out
  in plain words; a 10-second undo after the PIN; an optional trusted contact who must approve larger orders; refunds behind
  the same Readback + PIN.
- **Scam guard:** gift-card requests and classic pressure lines ("a caller says...", "keep it secret", "pay a fine") get a
  calm warning, and the order then needs the trusted contact's approval, who sees why it was flagged.
- **After the purchase, by voice:** "is this my package?" compares a delivery photo with the order (Gemini vision, always
  worded "photo suggests"); "it arrived broken" explains PayPal Purchase Protection and starts the refund; "what did I buy
  this week"; price-drop alerts on saved items, said once.
- **PayPal Pay in 4, read aloud:** when the total qualifies, the Readback says "4 payments of X" and "pay later" explains it.
  Sightline never picks credit for the shopper.
- **Browser extension prototype:** brings the same Readback + confirm + PIN gate to checkout pages, PayPal's first: it reads the
  page's own total and payee aloud and holds the pay button until the PIN. No network calls; the PIN is stored only as a hash.
- **Works with the tools people already use:** replies go to the user's own screen reader (NVDA, JAWS, VoiceOver) or an
  optional built-in voice, push-to-talk or typing, modifier-only shortcuts, large text and simple modes.

## How we built it
- **PayPal (sandbox):** Vault v3 saves the buyer's PayPal once through a full-page PayPal login (no popup). Each purchase is an
  Orders v2 `AUTHORIZE` with the saved `vault_id`; Sightline reads the Readback from PayPal's `amount.breakdown`, then captures
  on confirm + PIN or voids on cancel/undo. One `PayPal-Request-Id` per checkout attempt makes a repeated "confirm" safe.
  Refunds use the Payments v2 refund endpoint.
- **AI in three lanes for speed:** fixed commands and the whole checkout run with **no AI** (instant, deterministic);
  free-form requests go to a fast Gemini Flash-Lite model with tools (~0.5–1.5 s); heavy work runs **offline** — Gemini with
  vision writes accessible descriptions from product photos, which we reviewed by hand.
- **Stack:** Python, FastAPI, plain semantic HTML and JavaScript (role="log" transcript, aria-live, Web Speech push-to-talk),
  SQLite for order history, 180+ tests plus end-to-end browser tests of the extension, automated axe checks. Built in 16 days, at zero cost.

## Challenges we ran into
- PayPal's checkout normally needs a popup; we found that saving the wallet through a full-page redirect keeps PayPal's own
  login in charge of security while every later purchase stays voice-driven.
- Keeping AI out of the money path: the model kept "helpfully" restating prices, so prices never reach it at all.
- An early test returned the *peanut* trail mix for a "nut allergy" request, because the search matched the word "nut".
  Allergies became a hard filter in code.
- Making replies speak exactly once with a screen reader, and running on free-tier AI limits.

## Accomplishments that we're proud of
A complete purchase, refund and approval flow that a screen-reader user can do end to end, with every spoken amount traceable
to PayPal's data; and safety rules that hold even if the AI misbehaves.

## What we learned
Most AI accessibility tools *describe* things. The hard, unsolved part is AI that *acts* safely: reading back what will happen
and waiting for the person to decide.

## What's next for Sightline
Testing with blind and low-vision shoppers (this prototype has not yet been tested by them), real merchant catalogues,
taking the extension from look-alike test pages to PayPal's live checkout, and a version for older adults focused on scam
protection.

## Built with
python, fastapi, paypal-rest-api, paypal-vault, gemini, javascript, web-speech-api, aria, sqlite, playwright

## Honesty notes (keep in the submission)
- Sandbox only, fake money. The shop and its reviews are fictional demo data; photos are Wikimedia Commons (credited).
- The demo video's voices are synthetic; the shopper's speech is typed by a script and narrated.
- Pay Later is read aloud but not used: the vaulted checkout pays in full. Dispute help refunds through the demo store; it
  does not open a PayPal dispute. The scam guard is keyword rules, so it can miss or over-flag. The extension has been tested
  on local look-alike pages, not on live PayPal checkout.
