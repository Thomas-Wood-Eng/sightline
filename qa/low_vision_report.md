# Sightline: low-vision usability report (persona: Maria, 67, macular degeneration)

Scope: testing only, no app code changed (fixes came later: see Fix status). Server run on port 8790 with a separate QA database (`data/qa_lowvision.db`).
Screenshots: `C:\Projects\paypal_hackathon\qa\shots\`. Reproduction scripts: `C:\Projects\paypal_hackathon\qa\*.py`. Raw step log: `C:\Projects\paypal_hackathon\qa\notes.jsonl`.

## Summary of Maria's experience

Maria can get through the shopping path. Search, "tell me about the first one", reviews, adding with a size, the Readback, the PIN box, returns and the approval page all work, and the wording is plain. Text is large and readable at 200% and 400% with no horizontal scrolling, and the focus ring, dark mode and forced colours all hold up.

Three things would stop her trusting the app with money:

1. **The undo window is not clear.** The Escape key that the app tells her to press is swallowed by the spoken reply when the app voice is on. The countdown exists only as text in a log that scrolls away. The PIN box does not show the amount she is approving.
2. **A trusted-contact safety setting can be silently lost.** It can be lost when a settings save overlaps a payment capture. The app says "Saved", and a later order over the limit then goes straight to the PIN with no approval.
3. **The conversation log grows without limit above the message box.** After ten replies the message box sits about 5,500 px down the page. At 400% she has to scroll past the whole conversation to type.

## Fix status (2026-10-27)

All 12 bugs are fixed. Each fix has a regression test (`tests/test_lowvision_fixes.py`, `tests/test_browser.py`).
Re-checked on the live sandbox (port 8791): `qa/fix_race_live.py`, `qa/fix_refund_live.py`, `qa/debug_esc.py`,
`qa/debug_fresh.py`, `qa/debug_lock.py`, `qa/measure_drift.py`. Screenshots at 320 px (large text, about 400%), 1920 px
and in forced colours: `qa/fix_shots.py` (`shots/fix_*.png`). axe-core 4.10 (WCAG 2.2 AA + best practice): 0 violations
in light and dark, on the setup form, PIN box, undo box and after an undo (`qa/fix_axe.py`).

| # | Bug | Severity | Fixed | How it was checked |
|---|---|---|---|---|
| 1 | Trusted contact lost when a save overlaps a capture | blocker | Yes, commit d05bcb1. The cookie now holds only a signed session id; state lives server-side in SQLite (kept across restarts), and requests for one session run one at a time. | Test reproduces the interleaving; live re-run: the save waits about 2 s for the capture, the contact is kept, the next order goes to Alex. |
| 2 | Escape swallowed by the app voice | major | Yes, 1db1a27. One press stops the voice and undoes or cancels, with "Undoing the payment." shown and spoken (or announced). A key pressed during a request is queued, not dropped. | Browser test; `debug_esc.py`: state `voided` 0.3 s after the first Escape. |
| 3 | PIN box has no amount | major | Yes, f763d50. "Paying 59.59 US dollars to Sightline Demo Store", from PayPal's amount via the server. | Browser test; `shots/fix_320_forced_pin.png`. |
| 4 | No visible countdown | major | Yes, f763d50. Large "Paying in 7 seconds" beside Undo; announced only at the 5-second mark. | Browser test; `shots/fix_320_large_undo.png`. |
| 5 | Message box drifts down the page | major | Yes, 4730474. The log scrolls in its own box (max-height max(8rem, 45vh)), to the newest reply. | Browser test at 640 and 320 px; `measure_drift.py`: 481 px after 0, 6 and 10 replies. |
| 6 | No feedback during capture or undo | major | Yes, f763d50 and 1db1a27. "Paying now…" with Undo hidden, then the result in the box; "Undoing the payment." at once. | Browser test. |
| 7 | Completed refund reported as not refunded | major | Yes, 965dbdc (root cause: the stale cookie, fixed by bug 1). A return step whose line is already refunded is also cleared. | Test; live sandbox with the connection dropped after the PIN: state `idle`, "my orders" shows the refund, cancel says nothing is on hold. |
| 8 | Focus stays in the message box when a PIN is waiting | minor | Yes, f763d50. | Browser test. |
| 9 | Bare size "M" | minor | Yes, 684cd2a. Adds the item in focus in that size, or asks "Size M for which item? Say the number first..." and keeps the results. | Test; `debug_fresh.py`. |
| 10 | Lockout gives no clear way back | minor | Yes, 684cd2a. It names the steps: say link PayPal or use the "Link PayPal again" link in the PayPal section, log in, then choose a new PIN in Setup. | Test; `debug_lock.py`. |
| 11 | Approval link opens a new tab without warning | minor | Yes, 684cd2a. The link reads "Open the approval page (opens in a new tab)". | Browser test. |
| 12 | Settings PIN label omits the trusted contact | minor | Yes, 684cd2a. It reads "Current PIN, needed to change caps, PIN or trusted contact". | Test. |

## Bugs

Severity key: blocker / major / minor / polish.

### 1. Blocker: trusted-contact setting silently discarded after a save that overlaps a payment capture

- **WCAG:** not a WCAG item; relevant to 3.3.4 (error prevention for legal or financial data) in spirit.
- **Steps:**
  1. Reach an undo window (enter the PIN, then reload the page, or wait for the 10 s countdown).
  2. The page's finalize call starts a PayPal capture that takes about 2 to 3 s.
  3. Within about 1 s, open Settings, enter Contact name "Alex", email, approval threshold 50, current PIN, and press "Save settings". The status says "Saved. ... Alex approves orders over 50.00 US dollars."
  4. Wait 5 s and reload. The Trusted contact fields are empty.
  5. Check out a Heavyweight hoodie (Readback total 96.33 US dollars).
- **Expected:** the order is held for Alex's approval, with an approval link.
- **Actual:** the order goes straight to "Confirmed. Now type your 4-digit PIN", with no approval step and no approval link.
- **Evidence:** `shots\p4b_02_readback_big.png` (no approval line), `shots\p4b_04_after_pin_big.png`. Reproduced twice with `qa\debug_race.py`: a save 0.09 s after load persisted; a save at about 1 s, during the capture, returned 200 and then the contact was `null`.
- **Likely cause:** the session is a signed cookie. Each request writes its whole session back when it finishes. `/api/finalize` reads the session before the slow PayPal capture and writes it after, overwriting the settings change made in the meantime. The same overwrite could drop cart changes or chat-turn changes made during a capture. Not tested for those.

### 2. Major (safety): Escape does not undo the payment while the app voice is still speaking

- **WCAG:** 2.1.1 (keyboard) is met, but the action does not do what it says. Relevant to 2.2.1 (timing) and 3.3.4.
- **Steps:** Setup "No, the app reads replies" (or Settings: "The app voice"). Add an item, check out, confirm, type the PIN in the PIN box, press Enter, then press Escape straight away while the reply "PIN accepted. PayPal takes the payment in 10 seconds. To stop it, say undo, or press Escape..." is still being spoken.
- **Expected:** Escape voids the hold, as the Keyboard shortcuts section says.
- **Actual:** the voice stops, the Undo box stays on screen, and the server state is still `undo_window`. The first Escape is consumed by `speechSynthesis.cancel()` (the handler checks `speechSynthesis.speaking` first). Maria sees the voice stop and may think she has undone the payment. A second Escape is needed, and it only starts the PayPal void.
- **Evidence:** `shots\p6e_02_voice_esc1.png` (state still undo window after the first Escape), `qa\debug_esc.py` (keydown logged with `speaking=true`, no request sent). Headless Chromium may speak for longer than a real voice, so the duration is exaggerated; the precedence bug is not.
- **Screen-reader mode is not affected:** Escape undid the hold there (`shots\esc_sr_01.png`, `qa\debug_esc3.py`).

### 3. Major: the PIN box does not show what she is approving

- **WCAG:** 3.3.2 (labels or instructions for money entry), usability.
- **Steps:** Check out any item, press Confirm.
- **Expected:** the PIN box shows the amount, for example "Pay 36.74 US dollars".
- **Actual:** the box is headed "Approve the payment" with no amount. The Readback with the total is above it in the log and scrolled out of view.
- **Evidence:** `shots\p3_03_pin_box_view.png`, `shots\p8big_03_pin_box.png` (400%: heading and field only).

### 4. Major: the undo window has no visible countdown

- **WCAG:** 2.2.1 (timing), 3.3.4.
- **Steps:** Enter the correct PIN, then look at the screen for the next 10 seconds.
- **Expected:** a visible, updating countdown ("Paying in 7 seconds") beside the Undo button.
- **Actual:** the Undo box shows only "Undo payment (Escape)". The countdown is text in the log, which is far above at 400%. At 400% the Undo button sits under the Talk button, below the message box.
- **Evidence:** `shots\p3_05_undo_3s.png`, `shots\p8big_04_undo.png`.

### 5. Major: the message box drifts away from the top of the page as the conversation grows

- **WCAG:** usability; 2.4.3 (focus order) is not broken, but the reading and typing path is.
- **Steps:** Start a fresh session (640x360, 200%). Send "help" ten times with fixed commands.
- **Expected:** the message box stays near the top, or the log scrolls inside its own box.
- **Actual:** the message box top moves from 581 px (start) to 3,546 px (after 6 replies) to 5,522 px (after 10 replies). `#log` has `max-height: none`, so every reply pushes the form down.
- **Evidence:** `qa\measure_drift.py` output, `shots\drift_after10.png`.

### 6. Major: no feedback while PayPal is capturing or voiding

- **WCAG:** 3.3.1 / 4.1.3 (status messages); 2.2.1.
- **Steps:** Enter the PIN and let the countdown run out. The PayPal capture takes about 2 to 3 s.
- **Expected:** "Paying now" or similar as soon as the countdown ends.
- **Actual:** at 12 s after the PIN, the Undo button is still shown, and the last message still says "PayPal takes the payment in 10 seconds". The same happens after Escape: the undo takes about 3 s (state `undo_window` for 2 s, then "Undone"), with no "Undoing" message.
- **Evidence:** `shots\p3_07_paid.png` (undo box still visible at 12 s), `qa\debug_esc3.py` output (busy for about 3 s).

### 7. Major (money text): a refund that PayPal completed is reported as "not refunded"

- **WCAG:** not WCAG; money accuracy.
- **Steps:** Check the order (1 Heavyweight hoodie, 59.59 US dollars), say "return the hoodie", confirm, type PIN, then close the page 4 s later (before the reply came back). Reopen and say "my orders", then "cancel".
- **Expected:** the return is either complete or still waiting, and the message matches the order.
- **Actual:** the database row shows 54.60 US dollars refunded, and "my orders" says "54.60 US dollars refunded". But the session says "A return is waiting. Type your PIN", and "cancel" replies "Return cancelled. Nothing was refunded."
- **Evidence:** `shots\p6a_05_return_done.png` (PIN box still open), `shots\p6a3_01_orders.png`, the `orders` row for 1LJ97777J8758751B in `data\qa_lowvision.db`.
- **Confidence:** medium. I did not reproduce a clean reload, so this may be the same stale-session overwrite as bug 1. The contradiction between the database and the message is certain.

### 8. Minor: focus stays in the message box when a PIN is already waiting

- **WCAG:** 2.4.3 (focus order).
- **Steps:** With a payment already waiting for its PIN, send any reply that does not change the state (for example "check out", which answers "A payment is already on hold"). Then press Tab or type the PIN.
- **Expected:** focus moves to the PIN box.
- **Actual:** focus stays in the message box, and the PIN is typed there. The app blocks it ("For your safety, type the PIN in the PIN box, not the message box. Nothing was sent"), which is good, but Maria will not know where her typing went.
- **Evidence:** `shots\p6d_03_pin_ready_B_640.png` (focus on message), `shots\p6d_04_pin_400.png`. `setState` only moves focus when the state changes.

### 9. Minor: a bare size is answered with a confusing message and nothing is added

- **WCAG:** 3.3.2.
- **Steps:** Search "find me a warm hoodie". Without choosing a result, type "M".
- **Expected:** "Which one? Say the number first," or the item is added.
- **Actual:** "Both the first and second hoodies are available in a medium size." Nothing is added, but it reads as if the item was.
- **Evidence:** `qa\debug_fresh.py` output.

### 10. Minor: three wrong PINs lock the PIN with no clear way back

- **WCAG:** 3.3.1 (error identification), 3.3.4.
- **Steps:** At the PIN box, enter three wrong PINs.
- **Expected:** plain steps to unlock.
- **Actual:** "Your PIN is locked after three wrong tries. Nothing was charged. To unlock, link PayPal again, which needs your PayPal login, then set a new PIN. The hold was released." The lock is not explained beyond that, and the "Link PayPal" button is at the bottom of the page.
- **Evidence:** `shots\p7b_03_locked.png`; `qa\debug_lock.py` output shows the lock works.

### 11. Minor: the approval link opens a new tab with no warning and a long URL as its text

- **WCAG:** 3.2.5 (AAA), usability.
- **Steps:** Over-limit order, then the "Approval link: ..." line.
- **Actual:** the link has `target=_blank` and shows the full `http://127.0.0.1:8790/approve/...` string.
- **Evidence:** `shots\p5_02_readback.png`.

### 12. Minor: the Settings label for the current PIN is incomplete

- **WCAG:** 3.3.2.
- **Steps:** Settings, change only the trusted contact.
- **Expected:** the label mentions the trusted contact.
- **Actual:** the label reads "Current PIN, needed to change caps or PIN". The hint under the contact fields says changing the contact also needs the current PIN, and the server enforces that.
- **Evidence:** `app/main.py` `post_settings`; `app/static/index.html` labels.

## Suggestions (not bugs)

- Put the amount in the PIN box heading ("Pay 36.74 US dollars: type your PIN") and the same text in the Undo box.
- Show a live countdown in the Undo box with `aria-live="polite"`, updated once a second, and a "Paying now" state when the countdown ends.
- Let Escape act on the payment first while the app is in `awaiting_pin` or `undo_window`, and stop speech separately. Or use a different key for "stop talking".
- Give `#log` its own scroll height, or move the input above the log, so the message box does not drift.
- Move focus to the PIN box whenever the app asks for a PIN, not only on a state change.
- After a search, "add it" gives "Which one?". Maria would likely prefer "add the first one" to work, or the app to assume the first result when only one is shown.
- Setup's default "Yes, I use a screen reader" makes the app silent. For users who are not using a screen reader, consider defaulting to "No" or asking more plainly.
- The Setup form is long at 400% (about 1,100 px for two PINs and two caps). Consider splitting it into steps.

## What worked well (evidence)

- Reflow: no horizontal scroll at 320 px wide with large text on (`overflow` checks in `shots\p8big_01_results.png`, `shots\p8big_02_total.png`).
- Totals: the Readback "Total" line is bold and large at 400% (`shots\p8big_02_total.png`). The return Readback shows the refund split (item, tax, shipping not refunded).
- Focus: a 4 px focus ring is visible on the message box, PIN box and buttons in light, dark and forced-colour modes (`shots\p8dark_03_pin_box.png`, `shots\p8forced_03_pin_box.png`).
- Tab order is sensible: skip link, message, Send, Talk, Link PayPal, then Settings. Nothing in the order is hidden or unreachable (`qa\phase7.py`).
- Wrong PIN gives a clear count ("2 tries left"), and a PIN typed into the message box is not echoed or sent (`shots\p6c_04_pin_in_msgbox.png`).
- Typos and vague asks work: "find me a hodie" finds hoodies, "something nice for my granddaughter" finds gift items.
- Trusted-contact approval works in a clean session: the approval page is clear, approving leads to "Alex approved this order" and then the PIN (`shots\p5_04_approve_page.png`, `shots\p5_06_after_approval.png`).
- "Undo" typed in the message box works, with a clear reply ("Undone. Nothing was charged").

## Method and limits

- Playwright (Chromium, headless). Viewports: 640x360 at device scale 2 (about 200%), 320x480 at device scale 2 (about 400% reflow), with the app's large-text setting on for the 400% pass. Dark colour scheme and `forced_colors='active'` each got their own pass.
- No screen reader was used, as the persona specifies. Windows Magnifier was not used; browser viewport sizes stand in for zoom.
- Headless Chromium has no real TTS voices, so speech duration is not realistic. The Escape precedence bug (2) does not depend on duration.
- PayPal sandbox latency was about 1 to 3 s per call, which explains the feedback gaps (bug 6).
- AI-backed requests were paced to at most 4 per minute.
- Real sandbox payments were captured in the QA database (about 36.74, 96.33, 59.59 and 36.74 US dollars, one refund of 54.60 US dollars). The database is `data\qa_lowvision.db`, separate from the main demo data.
