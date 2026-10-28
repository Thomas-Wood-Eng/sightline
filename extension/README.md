# Sightline checkout guard (Chrome extension, prototype)

Brings Sightline's Readback + Confirm + PIN gate to real checkout pages, PayPal first.
When you press the final pay button ("Pay Now", "Complete Purchase", "Place order", ...), Sightline stops the press,
reads back "You are about to pay $45.67 USD to Bluebird Outfitters." in large text and out loud, and only presses the
button for you after you choose Confirm, type your PIN, and let a 10-second undo window run out.

**Prototype.** It reads totals and payees from the page with text heuristics, which can miss or misread. It never types
passwords or card details, and it never presses pay on its own: only after your Confirm and PIN.

Full guide, demo script and limits: [docs/extension.md](../docs/extension.md).

## Files

| File | What it does |
|---|---|
| `manifest.json` | Manifest V3. PayPal checkout pages only, unless you turn on a site yourself. |
| `detect.js` | Heuristics: which button is the final pay button, the total, the payee, scam words. Text and roles only, no class names. |
| `content.js` | Catches click / Enter / Space on that button (capture phase, at `document_start`), opens the dialog, re-presses the button after confirm. |
| `dialog.html`, `dialog.js` | The Readback dialog, in an extension frame so the shop's scripts cannot read the PIN. Focus trapped, Escape cancels. |
| `pin.js` | PIN check: salted SHA-256 via SubtleCrypto in `chrome.storage.local`; 3 wrong PINs lock for 5 minutes. |
| `popup.html`, `popup.js` | Popup and options page: on/off, this site, set/change PIN, read aloud, speaking speed. |
| `background.js` | Registers the guard on sites you opt in to; opens the settings page on first install. |
| `ui.css` | Shared styles: large text, high contrast, dark mode, forced colours, reflows at 400% zoom. |
| `test/` | Local fixture pages and the Playwright end-to-end test. |

## Permissions, and why

| Permission | Why |
|---|---|
| `storage` | Saves your settings and the salted hash of your PIN on this computer (`chrome.storage.local`). Never the PIN itself. |
| `activeTab` | Lets the popup read the address of the tab you opened it on, to offer "Check payments on this site". |
| `scripting` | Runs the guard on a site you turned on (`registerContentScripts`), and in that site's already-open tab. |
| Content script on `www.paypal.com` and `www.sandbox.paypal.com`, paths `/checkoutnow`, `/checkoutweb/`, `/checkout/`, `/webapps/` | The PayPal checkout pages it guards by default. These match patterns are its only built-in host access. |
| `optional_host_permissions` `https://*/*`, `http://*/*` | **Not granted at install.** Chrome asks you for one site at a time when you tick "Check payments on this site". Unticking removes it. |
| `web_accessible_resources` (dialog files, with `use_dynamic_url`) | So the dialog can be shown in a frame on the checkout page. The dynamic URL changes each session, so sites cannot probe for the extension. |

No network requests, no analytics, no remote code: every script ships in this folder, and MV3's default content
security policy blocks anything else.

## Test

    python -m pytest extension/test -q

Loads this folder unpacked into Playwright's Chromium (a test-only manifest copy adds `http://127.0.0.1/*` to the
content-script matches) and drives the pages in `test/fixtures/` over a local server. No PayPal login, no credentials.
Writes the screenshots in `screenshots/`.
