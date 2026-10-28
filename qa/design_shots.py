"""Design screenshots + axe, against an in-process server with the fake PayPal (no sandbox calls, real catalogue).
Usage: python qa/design_shots.py [prefix]   -> qa/shots/design/<prefix>_*.png, then axe results printed."""
import os, socket, sys, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(SIGHTLINE_NO_LLM='1', SIGHTLINE_DB=os.path.join(tempfile.mkdtemp(), 'shots.db'),
                  SIGHTLINE_UNDO_SECONDS='10', DEMO_VAULT_ID='TEST-VAULT')
sys.path.insert(0, str(ROOT / 'tests'))
from conftest import FakePayPal  # noqa: E402
from app import paypal  # noqa: E402
os.environ.update(SIGHTLINE_UNDO_SECONDS='10', SIGHTLINE_CATALOG='')  # conftest pins these for the tests

f = FakePayPal()
for name in ('create_hold', 'capture', 'void', 'get_order', 'refund'):
    setattr(paypal, name, getattr(f, name))

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from app.main import app  # noqa: E402

OUT = ROOT / 'qa' / 'shots' / 'design'
OUT.mkdir(parents=True, exist_ok=True)
PREFIX = sys.argv[1] if len(sys.argv) > 1 else 'after'
AXE = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js'

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
srv = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
threading.Thread(target=srv.run, daemon=True).start()
while not srv.started:
    time.sleep(0.05)
BASE = f'http://127.0.0.1:{port}'


def send(page, text):
    n = page.locator('#log .turn').count()
    page.fill('#message', text); page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=60000)


def axe(page, label):
    page.add_script_tag(url=AXE)
    r = page.evaluate("axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']})")
    v = [(x['id'], x['impact'], len(x['nodes']), x['nodes'][0]['target']) for x in r['violations']]
    print(f'axe {label}: {len(v)} violations {v}', flush=True)
    return len(v)


def setup(page, large=False):
    page.goto(BASE); page.wait_for_selector('#log .turn')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234'); page.click('text=Save and start')
    page.wait_for_selector('#setup', state='hidden')
    if large:
        page.evaluate("document.documentElement.classList.add('large')")


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f'{PREFIX}_{name}.png'), full_page=full)


total = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, opts in [('1920_light', (1920, 1080), {'color_scheme': 'light'}),
                           ('1920_dark', (1920, 1080), {'color_scheme': 'dark'}),
                           ('1280', (1280, 800), {}),
                           ('320_large', (320, 640), {}),
                           ('1280_forced', (1280, 800), {'forced_colors': 'active'})]:
        page = b.new_page(viewport={'width': vp[0], 'height': vp[1]}, **opts)
        page.goto(BASE); page.wait_for_selector('#log .turn')
        if name == '1920_light':
            shot(page, 'setup')
            total += axe(page, f'{name} setup')
        setup(page, large=name == '320_large')
        send(page, 'warm hoodie under 40 dollars'); send(page, 'add the first one in medium')
        shot(page, f'{name}_item')
        send(page, 'check out')
        shot(page, f'{name}_readback')
        if name in ('1920_light', '1920_dark'):
            total += axe(page, f'{name} readback')
        send(page, 'confirm'); page.wait_for_selector('#pin-form', state='visible')
        shot(page, f'{name}_pin')
        n = page.locator('#log .turn').count()
        page.fill('#pin', '1234'); page.press('#pin', 'Enter')
        page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}")
        print(page.locator('#log .turn').last.inner_text())
        page.wait_for_selector('#undo-box', state='visible')
        shot(page, f'{name}_undo')
        if name in ('1920_light', '1920_dark', '1280_forced'):
            total += axe(page, f'{name} undo')
        if name == '1920_light':
            page.click('#settings-more summary'); page.locator('details.how summary').click()
            shot(page, f'{name}_full', full=True)
            page.goto(BASE + '/approve/bad'); shot(page, 'approve_page')
        if name == '320_large':
            shot(page, f'{name}_full', full=True)
            sw = page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
            print('320 large horizontal overflow px:', sw)
        page.close()
    b.close()
print('TOTAL axe violations', total)
srv.should_exit = True
