"""Front-end regression tests in headless Chromium against an in-process server with the fake PayPal.
Skipped when Playwright or its Chromium is not installed."""
import socket, threading, time

import pytest

pw = pytest.importorskip('playwright.sync_api')

# a voice that never finishes on its own, like a long reply still being read aloud
FAKE_VOICE = """(() => {
  let speaking = false; window.__spoken = []; window.__cancels = 0;
  const synth = { get speaking() { return speaking; }, pending: false,
    speak(u) { window.__spoken.push(u.text); speaking = true; }, cancel() { window.__cancels++; speaking = false; } };
  Object.defineProperty(window, 'speechSynthesis', { configurable: true, get: () => synth });
})();"""


@pytest.fixture
def server(fake):
    import uvicorn
    from app.main import app
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    while not srv.started:
        time.sleep(0.05)
    yield f'http://127.0.0.1:{port}'
    srv.should_exit = True; th.join(5)


@pytest.fixture
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # browsers not downloaded
            pytest.skip(f'no Chromium: {e}')
        yield b
        b.close()


def open_app(browser, server, voice=False, width=1280, height=900):
    page = browser.new_page(viewport={'width': width, 'height': height})
    page.add_init_script(FAKE_VOICE)
    page.goto(server); page.wait_for_selector('#log .turn')
    page.check(f"input[name=screen_reader][value={'no' if voice else 'yes'}]")
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('text=Save and start'); page.wait_for_selector('#setup', state='hidden')
    return page


def send(page, text):
    n = page.locator('#log .turn').count()
    page.fill('#message', text); page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}")
    return page.locator('#log .turn').last.inner_text()


def to_pin(page):
    send(page, 'hoodie'); send(page, 'add it in medium'); send(page, 'check out'); send(page, 'confirm')
    page.wait_for_selector('#pin-form', state='visible')


def watch_status(page):
    """Collect every text #pay-status shows, since replies clear it quickly."""
    page.evaluate("""() => { window.__status = []; const el = document.getElementById('pay-status');
      new MutationObserver(() => window.__status.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); }""")


def last(page):
    return page.locator('#log .turn').last.inner_text()


# ---- bug 2: with the app voice talking, the first Escape undoes the payment and stops the voice ----
def test_escape_undoes_on_first_press_while_voice_speaks(browser, server, fake, monkeypatch):
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '10')
    page = open_app(browser, server, voice=True)
    to_pin(page)
    page.fill('#pin', '1234'); page.press('#pin', 'Enter')
    page.wait_for_selector('#undo-box', state='visible')
    assert page.evaluate('speechSynthesis.speaking')  # still reading "PIN accepted..."
    cancels = page.evaluate('window.__cancels')
    page.keyboard.press('Escape')
    assert page.evaluate('window.__cancels') > cancels  # voice stopped at once
    assert 'Undoing the payment.' in page.evaluate('window.__spoken')  # spoken feedback straight away
    page.wait_for_function("document.querySelector('#log .turn:last-child').innerText.includes('Undone')")
    assert fake.count('void') == 1 and fake.count('capture') == 0
    assert page.is_hidden('#undo-box')


def test_escape_cancels_hold_in_screen_reader_mode(browser, server, fake):
    page = open_app(browser, server)
    to_pin(page)
    watch_status(page)
    page.keyboard.press('Escape')
    page.wait_for_function("document.querySelector('#log .turn:last-child').innerText.includes('Cancelled')")
    assert 'Cancelling the payment.' in page.evaluate('window.__status')  # visible, and announced (role=status)
    assert fake.count('void') == 1 and page.evaluate('window.__spoken') == []  # screen reader mode: app stays silent
