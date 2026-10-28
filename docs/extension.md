# Sightline for any checkout (Chrome extension prototype)

The Sightline app's safety step, the Readback, works because Sightline owns the checkout. This extension carries the
same gate to checkout pages Sightline does not own, PayPal first:

1. You press the final pay button ("Pay Now", "Complete Purchase", "Place order", "Agree & Continue", ...) by mouse,
   Enter or Space.
2. Sightline stops that press before the page sees it and opens a dialog with the Readback, in large text and out loud:
   **"You are about to pay $45.67 USD to Bluebird Outfitters."** If it could not find the total it says so plainly:
   "Sightline could not find the total on this page. Check it before paying." Gift cards, wire transfers or crypto
   on the page add a warning line. If the amount on the button differs from the page total, it says that too.
3. You choose **Confirm**, then type your **PIN** (set in the extension popup; stored only as a salted SHA-256 hash).
   Three wrong PINs lock it for 5 minutes.
4. A **10-second undo window** is announced ("Paying in 10 seconds. Press Undo or Escape to stop."). Then Sightline
   presses the original button for you. Undo, Cancel or Escape at any point: nothing is paid, focus returns to the button.

It runs on PayPal checkout pages (`www.paypal.com` and `www.sandbox.paypal.com`, checkout and webapps paths) by default,
and on any other shop only when you tick **Check payments on this site** in the popup (Chrome then asks you for that
one site). Code and permission list: [extension/README.md](../extension/README.md).

## Load it unpacked

1. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**.
2. **Load unpacked**, choose the `extension/` folder.
3. The settings page opens. Set a 4 to 8 digit PIN. Optionally change the speaking speed, or turn off "Read the check
   aloud" if your screen reader already reads the dialog (otherwise you hear both).
4. Pin the extension to the toolbar to reach the popup quickly.

## 30-second demo (local fixture, no PayPal login)

The fixtures are local look-alike pages, so the demo never touches a real account. Serve them on 127.0.0.1 and let the
extension run there:

1. `python -m http.server 8765 --bind 127.0.0.1 --directory extension/test/fixtures`
2. Open http://127.0.0.1:8765/paypal_review.html, open the Sightline popup, tick **Check payments on this site**, accept
   Chrome's prompt. (Make sure a PIN is set.)
3. Script:
   - (0 s) Tab to **Complete Purchase**, press Enter. The page dims; the dialog says "You are about to pay $45.67 USD to
     Bluebird Outfitters."
   - (8 s) Press Enter on **Confirm**. Type a wrong PIN, Enter: "Wrong PIN. 2 tries left." Nothing paid.
   - (15 s) Type the right PIN, Enter: "PIN correct. Paying in 10 seconds." Press **Escape**: "Cancelled. Nothing was
     paid." Focus is back on the button.
   - (20 s) Optional: open http://127.0.0.1:8765/store_no_total.html, press **Pay now**: "Sightline could not find the
     total on this page" and the gift card / wire transfer warning.
4. To show the payment going through, repeat step 3 and let the 10 seconds run out: the page shows "Paid (1)".

Other fixture: `store_split.html` (total split across `<span>`s, pay button is a `div role=button`) reads back
"$49.19 to Acme Goods".

Screenshots (1920x1080): `extension/screenshots/modal_paypal_review.png`, `extension/screenshots/modal_no_total_scam.png`.

## Tests

`python -m pytest extension/test -q` (Playwright for Python, bundled Chromium, about 30 s). It loads the unpacked
extension, serves the fixtures on 127.0.0.1 through a test-only manifest copy, and checks: the press is intercepted
(click, Enter and Space on a `div role=button`, Enter in a form field), the Readback has the right amount and payee,
the PIN is stored only as a hash, a wrong PIN blocks, the right PIN plus the undo window lets the original click through
exactly once, Undo and Escape cancel and return focus, 3 wrong PINs lock, the off switch lets clicks through, focus is
trapped in the dialog.

## Limits (honest list)

- **Heuristics can miss.** Totals, payees and the pay button are found from visible words, not from PayPal's data.
  A page can word things differently, put the total in an image, or show several totals. Sightline says when it found
  nothing, but it can also find the wrong number. It is a second check, not a guarantee.
- **Not tested on live PayPal.** By design we never logged in; the PayPal look-alike fixture stands in for the review
  page. PayPal's real markup, wording and URL paths may differ and change.
- **Page can bypass it.** A shop's own script can submit without a click, act on `mousedown`/`pointerup`, or check
  `event.isTrusted` (the re-press is a script click). Payments started outside a recognised button are not caught.
- **The shop is not the adversary in this design.** The gate protects the shopper from a mistaken or misread payment;
  a hostile page could hide or overlay the dialog. The PIN is typed inside an extension frame, so the page cannot read it.
- **PIN strength.** A 4-digit PIN hashed with salted SHA-256 is a confirmation step, not encryption: anyone with access
  to the browser profile could brute-force it. It is never sent anywhere.
- **Voice.** Confirm is a button or keypress; there is no spoken "confirm" yet (the Sightline app has it).
- **Speech** uses the browser's built-in voice through the page; turn it off when a screen reader is running to avoid
  hearing both.
- Turning a site off takes effect after the page is reloaded. No icon set beyond one 192px image; no store listing.
