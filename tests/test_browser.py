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


def watch_status(page, el_id='pay-status', var='__status'):
    """Collect every text the element shows, since replies clear it quickly."""
    page.evaluate("""([id, v]) => { window[v] = []; const el = document.getElementById(id);
      new MutationObserver(() => window[v].push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); }""",
                  [el_id, var])


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
    assert page.is_hidden('#undo-btn') and page.inner_text('#countdown').startswith('Undone. Nothing was charged.')


def test_escape_cancels_hold_in_screen_reader_mode(browser, server, fake):
    page = open_app(browser, server)
    to_pin(page)
    watch_status(page); watch_status(page, 'pay-progress', '__progress')
    page.keyboard.press('Escape')
    page.wait_for_function("document.querySelector('#log .turn:last-child').innerText.includes('Cancelled')")
    assert 'Cancelling the payment.' in page.evaluate('window.__progress')  # visible at once
    # screen-reader issue 8: announced once, by the reply only (not also by the role=status region)
    assert 'Cancelling the payment.' not in page.evaluate('window.__status')
    assert page.get_attribute('#pay-progress', 'role') is None and page.get_attribute('#pay-progress', 'aria-live') is None
    assert fake.count('void') == 1 and page.evaluate('window.__spoken') == []  # screen reader mode: app stays silent


# ---- bug 3/4/6/8: the PIN box shows the amount and takes focus; the undo window shows a countdown, then "Paying now" ----
def test_pin_box_amount_focus_and_undo_countdown(browser, server, fake, monkeypatch):
    from app import paypal
    real = fake.capture
    monkeypatch.setattr(paypal, 'capture', lambda a, r: (time.sleep(1.5), real(a, r))[1])
    monkeypatch.setenv('SIGHTLINE_UNDO_SECONDS', '3')
    page = open_app(browser, server)
    to_pin(page)
    assert page.inner_text('#pin-amount') == 'Paying 41.73 US dollars to Sightline Demo Store'
    assert page.evaluate('document.activeElement.id') == 'pin'
    page.focus('#message'); send(page, 'check out')  # "already on hold": focus goes back to the PIN box
    assert page.evaluate('document.activeElement.id') == 'pin'
    watch_status(page)
    page.fill('#pin', '1234'); page.press('#pin', 'Enter')
    page.wait_for_selector('#undo-box', state='visible')
    assert page.inner_text('#undo-amount') == 'Paying 41.73 US dollars to Sightline Demo Store'
    assert page.inner_text('#countdown') in ('Paying in 3 seconds', 'Paying in 2 seconds')
    assert page.is_visible('#undo-btn')
    page.wait_for_function("document.getElementById('countdown').textContent === 'Paying now…'")
    assert page.is_hidden('#undo-btn')
    page.keyboard.press('Escape')  # too late: says so, sends nothing
    page.wait_for_function("document.getElementById('countdown').textContent.startsWith('Paid.')")
    assert page.is_hidden('#undo-btn') and fake.count('capture') == 1 and fake.count('void') == 0
    status = page.evaluate('window.__status')
    assert 'Last 5 seconds to undo. Press Escape or Undo.' not in status  # a 3-second window starts under 5 s
    assert 'Paying now.' in status and 'Too late to undo: PayPal is taking the payment now.' in status


# ---- bug 5: the log scrolls in its own box, so the message box does not drift down the page ----
@pytest.mark.parametrize('width,height', [(640, 360), (320, 480)])
def test_message_box_stays_put_as_log_grows(browser, server, fake, width, height):
    page = open_app(browser, server, width=width, height=height)
    top = lambda: page.evaluate("Math.round(document.getElementById('message').getBoundingClientRect().top + scrollY)")
    send(page, 'help')
    start = top()
    for i in range(6):
        send(page, ['what can i say', 'help'][i % 2])  # same reply; alternated, since an identical repeat within 1 s is ignored
    assert top() == start
    newest = page.evaluate("""(() => { const log = document.getElementById('log'), t = log.lastElementChild;
      return t.offsetTop >= log.scrollTop && t.offsetTop < log.scrollTop + log.clientHeight; })()""")
    assert newest  # the log scrolled to the newest reply
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')  # reflow


# ---- bug 11: the approval link says it opens a new tab, instead of showing a long URL ----
def test_approval_link_says_new_tab(browser, server, fake):
    page = open_app(browser, server)
    page.fill('#set-contact-name', 'Alex'); page.fill('#set-contact-email', 'alex@example.com')
    page.fill('#set-threshold', '20'); page.fill('#set-current-pin', '1234'); page.click('text=Save settings')
    page.wait_for_function("document.getElementById('settings-status').textContent.startsWith('Settings saved: Alex approves')")
    send(page, 'hoodie'); send(page, 'add it in medium'); send(page, 'check out')
    a = page.locator('#log a[href^="/approve/"]')
    assert a.inner_text() == 'Open the approval page (opens in a new tab)'
    assert a.get_attribute('target') == '_blank' and a.get_attribute('rel') == 'noopener'


# ---- screen-reader issue 1: a reload mid-checkout says what is on hold and restores the PIN box ----
def test_reload_mid_checkout_restores_context(browser, server, fake):
    page = open_app(browser, server)
    to_pin(page)
    page.reload(); page.wait_for_selector('#log .turn')
    welcome = last(page)
    assert welcome.startswith('Welcome back. A payment of 41.73 US dollars is on hold for Fleece')
    assert page.is_visible('#pin-form') and page.evaluate('document.activeElement.id') == 'pin'
    assert page.inner_text('#pin-amount') == 'Paying 41.73 US dollars to Sightline Demo Store'


# ---- screen-reader issue 2: a PIN-like message is shown and announced as "(number hidden)" in any state ----
def test_pin_like_message_never_echoed(browser, server, fake):
    page = open_app(browser, server)
    text = send(page, '1234')
    assert 'You: (number hidden)' in text and '1234' not in page.inner_text('#log')
    assert '1234' not in send(page, '12 34') + page.inner_text('#log')
    assert 'You: 2' in send(page, '2')  # short numbers are echoed as usual


# ---- screen-reader issue 3: a double Enter gives one reply ----
def test_double_enter_gives_one_reply(browser, server, fake):
    page = open_app(browser, server)
    send(page, 'hoodie'); send(page, 'add it in medium')
    n = page.locator('#log .turn').count()
    for _ in range(2):
        page.fill('#message', 'check out'); page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}")
    page.wait_for_timeout(1200)
    assert page.locator('#log .turn').count() == n + 1 and fake.count('hold') == 1


# ---- screen-reader issue 10: an empty Enter says what to do ----
def test_empty_enter_gives_hint(browser, server, fake):
    page = open_app(browser, server)
    n = page.locator('#log .turn').count()
    page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}")
    assert last(page) == 'Type a request first, or say help.'


# ---- screen-reader issue 11: a stale value in the current-PIN field is cleared after an error ----
def test_settings_error_clears_current_pin(browser, server, fake):
    page = open_app(browser, server)
    page.fill('#set-contact-name', 'Alex'); page.fill('#set-contact-email', 'alex@example.com')
    page.fill('#set-threshold', '20'); page.fill('#set-current-pin', '9999'); page.click('text=Save settings')
    page.wait_for_function("document.getElementById('settings-status').textContent.startsWith('Error')")
    assert page.input_value('#set-current-pin') == '' and page.evaluate('document.activeElement.id') == 'set-current-pin'
    page.keyboard.type('1234'); page.click('text=Save settings')
    page.wait_for_function("document.getElementById('settings-status').textContent.startsWith('Settings saved')")
