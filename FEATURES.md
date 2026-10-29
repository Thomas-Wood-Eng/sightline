# Sightline: feature backlog

Ideas beyond the MVP, roughly by value. ★ = strong for the hackathon video or judging; (S/M/L) = rough effort.
The MVP stays the 10 requirements in PLAN.md §6; nothing here starts before those pass.
✅ = built (Oct 27). Notes on the built versions: undo window is 10 s; trusted contact must approve (no notify-only mode)
and the link is shown instead of emailed; reviews are fictional demo reviews; tracking is PayPal order status plus the
catalogue's delivery estimate (no carrier tracking); gift mode has a note but no ship-to-another-address; verbosity
covers brief/normal/detailed, large text and simple mode.
Oct 28 batch: gift-card scam guard, package photo check, Pay in 4 read aloud, dispute help, compare (differences
only), wishlist price-drop alerts, purchase history by period. Notes are on each line below.

## Trust and safety (our core differentiator)
- ★ ✅ **Trusted contact** (M): optional family member or friend who gets a notification, or must approve, above a set amount. Also the seniors angle.
- ★ ✅ **Scam and dark-pattern guard** (M): flag pre-ticked add-ons, "only 2 left!" pressure, subscription traps, unusual shipping, and say so plainly.
- ★ ✅ **Gift-card / pressure scam guard** (M): fixed rules (no AI) catch gift-card requests and classic scam pressure
  (IRS, police, bank says, fines, wire, crypto, keep it secret, prize fees, grandchild in trouble). Gift card orders, and
  any order in a flagged session, need trusted-contact approval whatever the total; the approval page says why, with the
  shopper's words. The shopper chooses this in Settings (on by default, PIN to change); off, the warning stays, the order
  takes the usual Readback + confirm + PIN, and the contact (asked only over the amount) is never shown the shopper's
  words. No contact: refused, with how to add one. Note: the flag lapses after 24 hours or once the contact
  decides; keyword rules can miss new scripts and can flag an innocent sentence.
- ✅ **Undo window** (S): after "confirm", a 30-second "undo" that voids before capture (hold → capture delayed), if PayPal's timing allows.
- ✅ **Spending summary by voice** (S): "How much did I spend this week?", read from our ledger and PayPal transactions, never from the model.
  ✅ Purchase history: "what did I buy last month / this week", "show my PayPal purchases" list date, items, amount and
  PayPal order id from the ledger (at most 5 orders read out). Only orders placed through Sightline.
- **Receipt by email or text** (S): plain-text, screen-reader-friendly receipt; PayPal already emails one, so we'd link to it.
- **"That's wrong" learning** (M): feedback.jsonl already logs it; review weekly and fix descriptions or phrasing.

## Shopping experience
- ★ ✅ **Size and variant selection** (M): "add it in medium", "the black one"; listing sizes become choices; refuse to add without a size if sizes exist.
- ★ ✅ **Review summaries** (M): "what do people say about it?" → pros, cons and recurring complaints, labelled as reviews, from real review text (needs review data).
- ✅ **Saved preferences** (S): "I'm a size M", "no nuts ever" → applied to every search; changed only in Settings.
- ✅ **Order tracking** (S): "where's my order?" via PayPal Agent Toolkit `get_shipment_tracking`.
- ✅ **Returns and refunds by voice** (M): "return the hoodie" → PayPal refund behind the same Readback + PIN.
- ✅ **Reorder** (S): "order my usual coffee again".
- ✅ **Wishlist / "remind me when it's cheaper"** (M): "tell me if it gets cheaper", "alert me under 40 dollars"; target
  stored in SQLite, said once on the next turn after the price reaches it. The catalogue is static, so the demo uses
  `SIGHTLINE_DEMO=1` and `POST /api/demo/price` (off by default) to change a price. No email or push notification.
- ★ ✅ **"Is this my package?"** (M): a photo of the delivery (file input, camera on phones, or "check my package") is
  compared with the order's names, colours and catalogue photo descriptions by Gemini vision. Always "photo suggests",
  never certain; a mismatch offers "return it". Photo not stored; 10 MB limit; honest fallback when Gemini is down.
- ✅ **Dispute help** (S): "I never got my order", "it arrived broken", "this isn't what I ordered" → Purchase Protection in
  three sentences, then the usual refund Readback + PIN. Does not open a real PayPal dispute (demo store refunds directly).
- ✅ **Compare** (S): "compare those two", "compare 1 and 2", "which is better": only what differs (price, rating,
  reviews, arrival date, sizes; food allergens always), all from the catalogue.
- ✅ **Gift mode** (S): ship to another address, gift note read back before paying.
- ✅ **Pay Later** (M): when PayPal's total is 30 to 1500 USD the Readback adds "Pay in 4 may be available: 4 payments of
  X"; "pay later" explains it. Never selected for the shopper. Honest limit: the vaulted demo checkout pays in full; Pay
  in 4 is chosen on PayPal's own page, which this flow does not open. Venmo not built.

## Accessibility depth
- ★ **Real screen-reader polish** (M): NVDA/JAWS/VoiceOver passes, verbosity settings (brief / normal / detailed), speech-rate hints.
- ✅ **Low-vision mode** (S): extra-large product card, high-contrast themes, magnifier-friendly layout.
- **Braille display friendliness** (S): short lines, no decorative characters, abbreviations off.
- ✅ **Cognitive-friendly mode** (S): one choice at a time, plain language, slower pace.
- **Languages** (L): French first (Canada); Gemini handles the language, templates need translating.
- ✅ **Phone app / PWA** (M): installable, works with VoiceOver and TalkBack on mobile.
- **Wake word / hands-free** (M): optional; push-to-talk stays the default.

## Bigger directions
- ★ **Sightline for any store** (L): a browser extension that brings the Readback + confirm + PIN pattern to real checkouts (PayPal's own checkout first).
- **Merchant SDK** (L): a merchant drops in "accessible checkout by Sightline" and gets a WCAG-tested, voice-first checkout for their catalogue.
- **Seniors edition** (L): same safety core, plus trusted contact, scam guard and unhurried pacing (see the earlier discussion).
- **Accessibility QA agent** (L): an AI that drives a real screen reader through a site and reports what blind users would hit (separate product idea).

## Engineering
- ✅ Pin the concrete Gemini model before submission; add a Claude option in llm.py.
- ✅ (orders) Persist the ledger and lockouts (SQLite) instead of process memory. Lockouts, undo and approvals are still in memory.
- Speech in the browser (on-device recognition where Chrome supports `processLocally`) for privacy.
- Load test the free-tier limits for judging week; add a cached-answers mode if limits bite.
