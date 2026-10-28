# Sightline: screen-reader approximation test (Dev persona, keyboard only)

Date: 2026-10-27. Server: `uvicorn app.main:app --port 8792`, `SIGHTLINE_DB=data/qa_sr.db`, `DEMO_VAULT_ID` from `spike_state.json`.
Harness: `qa/sr/harness.py` plus `stage1.py` to `stage6e.py`. Raw logs: `qa/shots/sr/*_log.json` (every "spoken" and focus event with a timestamp in ms).

**Not real NVDA.** "Spoken" means text added to an aria-live / role=log / role=status / role=alert region (MutationObserver). "Focus" means `focusin` with an approximate accessible name, role and description. Text from several `<p>` elements is concatenated, so run-together words such as "403 results" are an artifact of the harness, not something NVDA would say.

## Verdict (as Dev)

The bones are good. Replies arrive once, in a sensible order. The Readback reads item, quantity, unit price, shipping, tax, total, delivery and seller in that order. The PIN box names the amount ("Paying 36.74 US dollars to Sightline Demo Store") in its description. The 5-second undo warning and "Paid" are each announced once, and Escape with a hold cancels cleanly. Settings errors are announced and focus returns to the field. Two things would make me stop trusting it. First, a reload mid-checkout wipes the transcript and says only "Welcome back", while the server still holds the payment, so I would not know money was on hold. Second, a PIN typed into the message box while an order awaits approval is echoed on screen and into the log that NVDA reads. Replies are also too long at the default "Normal" setting, and there are several double announcements. I would not hand this to a blind shopper for real money until the two major items are fixed.

## Fix status (2026-10-27)

Regression tests: `tests/test_screenreader_fixes.py` (server) and `tests/test_browser.py` (headless Chromium). Full suite: 161 passed, 2 skipped; live sandbox tests pass.
Re-check: `SR_BASE=http://127.0.0.1:8811 python qa/sr/recheck.py` against the live sandbox (keyword search, no Gemini): 15 of 15 checks pass. The log is in `qa/shots/sr/recheck_log.json`. axe-core 4.10 (`qa/fix_axe.py 8811`): 0 violations in light and dark mode, on the setup form, PIN box, undo box and after an undo.

| # | Issue | Fixed | How |
|---|---|---|---|
| 1 | Reload mid-checkout hides the hold | Yes, 44a939d | The welcome message is built from server data, for example "Welcome back. A payment of 36.74 US dollars is on hold for Fleece-lined pullover hoodie (size M, heather grey). Say repeat to hear the Readback, confirm to continue, or cancel to release it." It covers awaiting confirm, PIN, approval, the undo window (countdown restored) and a pending refund. In the PIN state the PIN box is shown and focused. During a hold, "repeat" reads the Readback, not the last reply. |
| 2 | PIN echoed in the message box | Yes, 4a6267b | In every state, a message of only digits with 4 or more of them is shown and announced as "You: (number hidden)". Outside the PIN step, the server gives one fixed reply that does not reveal whether the digits match the PIN. Picks and sizes such as 2 or 32 still work. |
| 3 | Double Enter gives two Readbacks | Yes, 2d59b9e | The page ignores the same text sent again while the first is in flight or within 1 s. On the server, a repeated "check out" while a hold exists places nothing new and replies in one short line ("No new hold was placed. A payment of ... is on hold ..."). |
| 4 | 98-word describe; default was Normal | Yes, 079d94d, fbad7cc | Brief is now the default. The brief describe gives the name, one sentence, then price and delivery (about 40 words). "More", "tell me more" and "details" go one level up. Brief results keep name, price and rating, in 15 words or fewer. |
| 5 | "You:" echo is part of the announced reply | No | Not in this round's scope. Needs a real NVDA check of how a separate, non-live echo would read in browse mode. |
| 6 | "add it" after a search | Yes, bf92080 | "Which one: 1, Fleece-lined pullover hoodie, 2, Organic cotton crew-neck, or 3, Cotton bath towel?" With exactly one result, the item is added. |
| 7 | Settings save repeats the summary | Yes, 7e0efff | "Settings saved:" plus only what changed, in 15 words or fewer (for example "Settings saved: Sam Test approves orders over 50.00 US dollars."). If more changed, it gives a count and says "say settings" for the rest. |
| 8 | Cancel and undo announced twice | Yes, 7e0efff | Escape's "Cancelling / Undoing the payment." now goes to a non-live line, so it is shown at once and the screen reader hears only the reply. With the app voice on, it is still spoken at once (the low-vision fix 2 is kept). |
| 10 | Empty Enter is silent | Yes, 7e0efff | "Type a request first, or say help." |
| 11 | Stale current-PIN field error (unverified) | Yes, real, 7e0efff | Cause: a stray keystroke left one blank character in New PIN. The server read it as a new PIN and said "The PIN must be exactly 4 digits." A blank New PIN now means keep. A bad new PIN is checked first and the error names it ("The new PIN must be ..."). After any error the current-PIN field is cleared, so a retype works despite maxlength. |
| 12-16 | Radio hint, stale "confirm", Setup summary, skip link, link position | No | Polish, not in this round. |

## Key moments (announcement log excerpts)

Times are ms from page load. "SPOKEN" is what the log region would announce.

**Checkout (stage3, stage3b)**
```
4557 SPOKEN #log | You: check outPayPal is holding the payment. Here is the Readback.Item 1: Fleece-lined pullover hoodie (size M, heather grey). Quantity 1. Unit price 34.99 US dollars.Shipping: 0.00 US dollars.Tax: 1.75 US dollars.Total: 36.74 US dollars.Delivery by Friday, October 30.Seller: Sightline Demo Store.Say confirm to continue to your PIN, or cancel to release the hold.
```
(54 words of reply. Announced once. Order is right. Total is stated explicitly.)

**PIN (confirm)**
```
7223 FOCUS [input[password]] "PIN, 4 digits" desc="Paying 36.74 US dollars to Sightline Demo Store" #pin
7223 SPOKEN #log | You: confirmConfirmed. Now type your 4-digit PIN in the PIN box and press Enter. Or say cancel.
```
Focus moves to the PIN field with the amount in its description. Good. The reply is announced at the same moment as the focus change, so NVDA may cut one of them off. That needs checking with real NVDA.

**Wrong PIN (stage6b)**
```
SPOKEN #log | You: PIN entered / That PIN is not right. 2 tries left.
focus: [input[password]] "PIN, 4 digits" ... (value cleared, focus stays in PIN field)
```

**Undo window (stage3b, correct PIN, no keys pressed)**
```
7252 FOCUS  [input[text]] "Message" (focus returns to the message box after PIN)
7252 SPOKEN #log | You: PIN enteredPIN accepted. PayPal takes the payment in 10 seconds. To stop it, say undo, or press Escape, or use the Undo button.
  countdown #countdown updates every second, not a live region: silent (correct)
12251 SPOKEN #pay-status | Last 5 seconds to undo. Press Escape or Undo.
17555 SPOKEN #pay-status | Paying now.
```
Tab order during the window from the message box: Send, Talk, "Undo payment (Escape)" (3rd Tab), Link PayPal again, My screen reader radio.

**Undo with Escape (stage3)**
```
8925 SPOKEN #log | PIN accepted. PayPal takes the payment in 10 seconds...
12367 SPOKEN #pay-status | Undoing the payment.
13503 SPOKEN #log | You: undoUndone. Nothing was charged. PayPal released the hold. Your cart is unchanged.
```
Focus stays in the message box. Two announcements in quick succession (see issue 8).

**Paid (stage3b and stage6b)**
```
19616 SPOKEN #log | Paid. PayPal captured 36.74 US dollars. Order number 7F973446R6470830J. Say spell that to hear the order number letter by letter.
```
Announced once, after the window ends.

**Approval over the threshold (stage5, stage5c)**
```
SPOKEN #log | ...Sent to Sam Test for approval. When Sam Test approves, say confirm and type your PIN. ... Approval link: Open the approval page (opens in a new tab)
approval page: Tab 1 = "Approve this order" button, Tab 2 = "Decline this order". Enter approves. Page reads "Approved / Thank you..."
main tab: "confirm" -> "Sam Test approved this order. Confirmed. Now type your 4-digit PIN..." focus moves to PIN field, description "Paying 62.99 US dollars to Sightline Demo Store".
```
Server captured $62.99 (`spent_today` 99.73 = 36.74 + 62.99). Caveat: in that run my tab was in the background while the window ran, and "Paid" did not show in the log within 12 s. The server had captured, so this may be a timer throttle in my test, not an app bug. Not re-verified.

**Refund (stage6a)**
```
Return Readback: "Refund: 36.74 US dollars. That is the item, 34.99 US dollars, plus its tax, 1.75 US dollars. Shipping is not refunded. ... Say confirm to continue to your PIN, or cancel to keep the item."
PIN focused: "Refunding 36.74 US dollars to your PayPal"
SPOKEN: Refunded 36.74 US dollars to your PayPal. PayPal says the refund is completed.
```

## Issue list

Severity: blocker / major / minor / polish.

**1. MAJOR (money state, WCAG 3.3.4 and 4.1.3 spirit): reload mid-checkout hides an active payment hold.**
- Repro: "warm hoodie under 40", "next", "add it", "medium", "check out". Reload the page (F5).
- Expected: the page says a payment is on hold, with the amount, and how to confirm or cancel.
- Actual: the transcript is gone. The page says only "Welcome back. What would you like to shop for?". The server still has `state=awaiting_confirm`, `pay="Paying 36.74 US dollars..."` (checked via `/api/settings`). Nothing in the page mentions it.
- Evidence: `qa/shots/sr/stage6d_log.json`. Pressing Escape later did cancel the hold (issue 9 is the good news).

**2. MAJOR (privacy and safety, WCAG 3.3.8 and 4.1.2): a PIN typed into the message box is echoed as plain text.**
- Repro: reach "awaiting approval" (trusted contact). Type `1234` into the message box and press Enter. The state is not awaiting_pin, so the echo is not hidden.
- Actual: the log shows `You: 1234`, spoken by NVDA, and kept on screen. The same happens in the idle state: `You: 9999`.
- Cause: `app.js` `const hide = state === 'awaiting_pin' && ...`. Only that one state is covered.
- Evidence: stage5 output, "APPROVAL REPLY: You: 1234"; stage6b, "You: 9999".
- Fix suggestion: hide any short digit-only message in every state, or refuse digit-only text with a fixed reply that does not echo it.

**3. MAJOR (requirement 2, announce once): a double Enter on "check out" appends two Readbacks.**
- Repro: type "check out", Enter, type "check out", Enter immediately.
- Actual: `turns added: 2`. The second is queued and produces a second full Readback, which NVDA reads again. The server state stayed single (`awaiting_confirm`).
- Caveat: I counted the turns but did not capture the second text, so the content of the second reply is unverified.

**4. MINOR: "tell me about the first one" is 98 words at Normal verbosity.**
- Evidence: stage2 log, `tell me about the first one`, reply 98 words including the "You:" echo. The Readback is 54 words. Repeated speech and echo make this worse.
- Also the default is "Normal" (Setup says "Replies are normal."). research_ux.md says brief by default. Mismatch.

**5. MINOR: "You: ..." echo is read aloud with every reply.**
- The user's own text is part of the same log entry, so NVDA repeats what I just typed each time ("You: nextNumber 1: ..."). Consider keeping the echo out of the announced region, or announcing only the reply.

**6. MINOR: "add it" right after a search asks "Which one?" instead of using the first result.**
- Repro: "warm hoodie under 40", then "add it".
- Actual: `Which one? Say a number from the results, or search first.`
- After "next", "add it" works. The first-result default is missing. Consider "Which one? Say a number." for clarity.

**7. MINOR: Settings save repeats the full account summary every time.**
- Repro: change any setting, then Save.
- Actual: "Saved. Per-order cap 100.00 US dollars. Daily cap 250.00 US dollars, 36.74 US dollars spent today. Replies are read by your screen reader. PayPal is linked. PIN is set. Replies are detailed. Caps, PIN and preferences can only be changed in the Settings form." About 50 words, every save, including amounts that did not change.

**8. MINOR (announce once): cancel and undo double-announce.**
- Escape with a hold: `Cancelling the payment.` (pay-status), then `Cancelled. PayPal released the hold...` (log), within 2 s.
- Undo: `Undoing the payment.` then `Undone. Nothing was charged...`.
- Not a failure, but NVDA will read two sentences that say the same thing.

**9. OK (recorded for the report): Escape with a hold cancels it; Escape with nothing held is silent.**
- Verified: `awaiting_confirm` then Escape gives `voided`. A second Escape with nothing held gives no speech.

**10. MINOR: empty Enter in the message box gives no feedback.**
- Repro: press Enter with the message box empty. Nothing is added to the log and nothing is spoken. This is a silent no-op, which the persona dislikes.

**11. MINOR, unverified: a settings save with an old 4-digit value in the current-PIN field returned "The PIN must be exactly 4 digits."**
- Stage4, second attempt. The field still held `9999` after a wrong PIN error, and I typed `1234` with no effect (maxlength), so the field kept `9999`. The message seems wrong for a 4-digit value. Not reproduced in stage4b, where a clean retype worked. Needs a targeted retest.

**12. MINOR: radio groups in Settings need arrow keys.**
- Tab lands only on the checked radio (verbosity "Normal" -> `Tab=5` to Normal). Brief and Detailed need arrow keys. This is standard radio behaviour, but nothing says so. A hint would help.

**13. POLISH: stale reply to "confirm" with nothing to confirm.**
- Repro after a paid order: "confirm" returns `Already paid, nothing more to confirm. Order number 48U47761PB087133G.`. Accurate, but it is a surprise for a user who just said confirm to nothing.

**14. POLISH: Setup "Setup saved." reply is about 50 words and spoken at once.**
- Includes caps, PIN status and verbosity. A short version with "Settings" for the rest would do.

**15. POLISH: skip link is the first focus stop, before Setup.**
- Tab 1 is "Skip to the message box". While Setup is visible it jumps past the setup form. It is correct, but a Dev who wants Setup first has to know to ignore it.

**16. POLISH: approval reply and approval link position.**
- The link sits in the log, before the message box. My forward Tab search from the message box took 21 presses, so I did not reach it that way. Shift+Tab from the message box should reach it first (inferred from DOM order, not measured).

**Positives (observed):** Readback order and total; PIN description carries the amount; 5-second warning once; "Paid" once; wrong PIN "2 tries left" with focus kept; approval page keyboard order (Approve first); settings error with focus back on the field; countdown silent; undo button reachable 3 Tabs from the message box.

## Suggestions

1. On load, show and announce any active hold or pending approval (persist the last reply, or ask the server for the pending state).
2. Hide the echo of any digit-only message in all states, or refuse it with a fixed reply.
3. Ignore a second submit while a request is pending, instead of queuing a second Readback.
4. Default to "brief" as research_ux.md says, and keep the echo out of the announced text.
5. Make Settings status short ("Saved.") and speak changes only.
6. Say something for an empty submit, and make "Cancelling / Undoing" a single announcement.
7. Retest issue 11 in isolation.

## Limits: not real NVDA. Verify these with a real screen reader

- **Real speech:** NVDA can cut off a reply when focus moves in the same instant (PIN focus plus reply). Check the order and whether the PIN prompt is heard.
- **Paragraph splitting:** the harness joins `<p>` text. NVDA reads each paragraph separately. Check run-together issues such as "403 results" and the "You:" echo.
- **Role=log behaviour:** how NVDA handles `aria-relevant="additions"` and `tabindex=0` on the log, and whether it re-reads the log when focus returns to it.
- **Speech speed and queueing:** the 5-second warning, "Paying now.", and "Paid" arrive while the user may be typing. Test interruption.
- **Radio and fieldset names:** the legend ("Are you using a screen reader?") is not part of my focus description. Confirm NVDA reads legend, label and state.
- **Approval page and new tab:** that NVDA announces the new tab and reads the page title and Approve button correctly.
- **Browse vs focus mode:** the log is a role=log and the Dev may be in browse mode. Check that the reply is found and read exactly once.
- **Verbosity default and timing:** check the 98-word reply at real speed, and whether a Dev would skip it.
- **Issue 11:** retest the settings error sequence, in case it is a real bug.
- **Voice input:** Talk (Alt+Shift+M) was not tested (headless browser, no microphone). Check `aria-pressed` and the Listening label.
- **Stray files:** an earlier path bug (`/c/...` used from Python on Windows) created `C:\c\Projects\paypal_hackathon\qa\shots\sr\` (stage logs and state). I copied those files into the correct folder and tried to delete `C:\c`, but the safety check blocked the removal. Please delete `C:\c` by hand. It is not part of the app.
