"""End-to-end: load the unpacked extension in Chromium and drive local fixture pages. No PayPal, no credentials.

Run from the repo root:  python -m pytest extension/test -q        (about 40 s: the undo window is real time)
"""
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

EXT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
SHOTS = EXT / "screenshots"
PIN = "2468"
DIALOG = 'iframe[title="Sightline payment check"]'


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(FIXTURES)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    # Test-only copy that also matches the fixture host; the shipped manifest stays PayPal-only.
    ext = tmp_path_factory.mktemp("ext") / "sightline"
    shutil.copytree(EXT, ext, ignore=shutil.ignore_patterns("test", "screenshots"))
    manifest = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
    manifest["content_scripts"][0]["matches"].append("http://127.0.0.1/*")
    (ext / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # Silent tests: Windows speech bypasses Chromium's audio, so stub it in every extension script of the copy.
    for js in ext.glob("*.js"):
        js.write_text("if (self.speechSynthesis) speechSynthesis.speak = () => {};\n" + js.read_text(encoding="utf-8"),
                      encoding="utf-8")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp_path_factory.mktemp("profile")), channel="chromium", headless=True,
            viewport={"width": 1920, "height": 1080},
            args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--mute-audio"],
        )
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        yield ctx, sw, sw.url.split("/")[2]
        ctx.close()


@pytest.fixture
def page(browser):
    pg = browser[0].new_page()
    yield pg
    pg.close()


def storage(sw, **values):
    sw.evaluate("v => chrome.storage.local.set(v)", values)
    return sw.evaluate("() => chrome.storage.local.get(null)")


def open_dialog(page, url, how="click"):
    page.goto(url)
    if how == "click":
        page.click("#pay")
    else:
        page.focus("#pay")
        page.keyboard.press(how)
    dlg = page.frame_locator(DIALOG)
    expect(dlg.locator("#confirm")).to_be_focused()
    return dlg


def close_with(page, target, key):
    # Element-level press() can hang when the frame is removed mid-keystroke, so press via the page keyboard.
    target.focus()
    page.keyboard.press(key)


def enter_pin(dlg, pin):
    dlg.locator("#pin").fill(pin)
    dlg.locator("#pin").press("Enter")


def test_popup_sets_pin_and_stores_only_a_hash(page, browser):
    _, sw, ext_id = browser
    page.goto(f"chrome-extension://{ext_id}/popup.html")
    page.fill("#new", PIN)
    page.fill("#repeat", "9999")
    page.click("text=Save PIN")
    expect(page.locator("#status")).to_have_text("The two new PINs do not match.")
    page.fill("#repeat", PIN)
    page.click("text=Save PIN")
    expect(page.locator("#status")).to_have_text("PIN saved.")
    expect(page.locator("#current")).to_be_visible()  # changing it later needs the current PIN
    saved = storage(sw)
    assert len(saved["pinHash"]) == 64 and len(saved["pinSalt"]) == 32
    assert PIN not in json.dumps(saved)


def test_paypal_lookalike_readback_wrong_pin_then_pay(page, base):
    dlg = open_dialog(page, f"{base}/paypal_review.html")
    expect(dlg.locator("#readback")).to_have_text("You are about to pay $45.67 USD to Bluebird Outfitters.")
    expect(dlg.locator("#notices li")).to_have_count(0)
    expect(page.locator("#result")).to_have_text("Not paid")
    dlg.locator("#confirm").press("Tab")  # focus trap: Confirm -> Cancel -> back to Confirm
    dlg.locator(".cancel").first.press("Tab")
    expect(dlg.locator("#confirm")).to_be_focused()
    page.wait_for_timeout(500)
    page.screenshot(path=str(SHOTS / "modal_paypal_review.png"))

    dlg.locator("#confirm").press("Enter")
    expect(dlg.locator("#pin")).to_be_focused()
    expect(dlg.locator("#confirm")).to_be_hidden()  # one step at a time: no stale Confirm beside the PIN
    enter_pin(dlg, "1111")
    expect(dlg.locator("#pin-msg")).to_have_text("Wrong PIN. 2 tries left.")
    expect(page.locator("#result")).to_have_text("Not paid")

    enter_pin(dlg, PIN)
    expect(dlg.locator("#count")).to_contain_text("Paying in")
    expect(dlg.locator("#undo")).to_be_focused()
    expect(dlg.locator("#confirm")).to_be_hidden()
    expect(dlg.locator("#pin")).to_be_hidden()
    expect(page.locator("#result")).to_have_text("Not paid")
    expect(page.locator("#result")).to_have_text("Paid (1)", timeout=13_000)  # after the 10 s undo window
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator("#pay")).to_be_focused()


def test_split_total_and_div_button_keyboard_escape(page, base):
    for key in ("Enter", " "):
        dlg = open_dialog(page, f"{base}/store_split.html", how=key)
        expect(dlg.locator("#readback")).to_have_text("You are about to pay $49.19 to Acme Goods.")
        close_with(page, dlg.locator("#confirm"), "Escape")
        expect(page.locator(DIALOG)).to_have_count(0)
        expect(page.locator("#pay")).to_be_focused()
        expect(page.locator("#result")).to_have_text("Not paid")  # the page's own keydown handler never ran


def test_undo_cancels(page, base):
    dlg = open_dialog(page, f"{base}/store_split.html")
    dlg.locator("#confirm").click()
    enter_pin(dlg, PIN)
    close_with(page, dlg.locator("#undo"), "Enter")
    expect(page.locator(DIALOG)).to_have_count(0)
    page.wait_for_timeout(1500)
    expect(page.locator("#result")).to_have_text("Not paid")


def test_no_total_and_scam_words_via_enter_in_form(page, base):
    page.goto(f"{base}/store_no_total.html")
    page.fill("#email", "sam@example.com")
    page.press("#email", "Enter")  # implicit form submission clicks the "Pay now" submit button
    dlg = page.frame_locator(DIALOG)
    expect(dlg.locator("#readback")).to_have_text("You are about to pay an amount Sightline could not read on 127.0.0.1.")
    notices = dlg.locator("#notices")
    expect(notices).to_contain_text("Sightline could not find the total on this page. Check it before paying.")
    expect(notices).to_contain_text("this page mentions gift cards and wire transfers")
    expect(dlg.locator("#confirm")).to_be_focused()
    page.wait_for_timeout(500)  # let the out-of-process frame paint before the screenshot
    page.screenshot(path=str(SHOTS / "modal_no_total_scam.png"))
    close_with(page, dlg.locator(".cancel").first, "Enter")
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator("#result")).to_have_text("Not paid")


def test_three_wrong_pins_lock(page, base, browser):
    dlg = open_dialog(page, f"{base}/paypal_review.html")
    dlg.locator("#confirm").click()
    for _ in range(3):
        enter_pin(dlg, "0000")
    expect(dlg.locator("#pin-msg")).to_contain_text("Too many wrong PINs. Sightline is locked until")
    expect(dlg.locator("#pin")).to_be_hidden()
    close_with(page, dlg.locator(".cancel").last, "Enter")

    dlg = open_dialog(page, f"{base}/paypal_review.html")  # the right PIN cannot even be tried while locked
    dlg.locator("#confirm").click()
    expect(dlg.locator("#pin-msg")).to_contain_text("locked until")
    expect(dlg.locator("#pin")).to_be_hidden()
    close_with(page, dlg.locator(".cancel").last, "Escape")
    expect(page.locator("#result")).to_have_text("Not paid")
    storage(browser[1], lockUntil=0, fails=0)


def test_off_switch_lets_clicks_through(page, base, browser):
    storage(browser[1], enabled=False)
    try:
        page.goto(f"{base}/paypal_review.html")
        page.click("#pay")
        expect(page.locator("#result")).to_have_text("Paid (1)")
        expect(page.locator(DIALOG)).to_have_count(0)
    finally:
        storage(browser[1], enabled=True)
