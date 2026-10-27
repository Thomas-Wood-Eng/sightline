"""Helpers for the low-vision persona run (Maria). Drives the app like a keyboard/mouse user; no app code touched."""
import json, os, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get('QA_BASE', 'http://127.0.0.1:8790')
SHOTS = os.path.join(os.path.dirname(__file__), 'shots')
NOTES = os.path.join(os.path.dirname(__file__), 'notes.jsonl')
os.makedirs(SHOTS, exist_ok=True)

# AI-backed free-form questions are paced to <= 4/min (15s gap, a little slack).
AI_GAP = 16.0
_last_ai = [0.0]


def note(step, kind, detail, shot=None):
    rec = {'t': time.strftime('%H:%M:%S'), 'step': step, 'kind': kind, 'detail': detail, 'shot': shot}
    with open(NOTES, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'[{kind}] {step}: {detail}' + (f' -> {shot}' if shot else ''), flush=True)


def shot(page, name):
    path = os.path.join(SHOTS, name + '.png')
    page.screenshot(path=path)
    return path


def overflow(page):
    """Horizontal page scroll at this viewport? (WCAG 1.4.10 reflow)."""
    return page.evaluate('() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})')


def turns(page):
    return page.locator('#log .turn').count()


def last_turn(page):
    t = page.locator('#log .turn').last
    return t.inner_text()


def send(page, text, ai=False, wait=1.0):
    """Type into the message box like Maria: click the box, type, press Enter."""
    if ai:
        gap = AI_GAP - (time.time() - _last_ai[0])
        if gap > 0:
            time.sleep(gap)
        _last_ai[0] = time.time()
    before = turns(page)
    page.click('#message')
    page.fill('#message', '')
    page.keyboard.type(text, delay=30)
    page.keyboard.press('Enter')
    deadline = time.time() + 45
    while time.time() < deadline:
        if turns(page) > before:
            break
        time.sleep(0.2)
    time.sleep(wait)
    return last_turn(page)


def type_pin(page, pin, field='#pin'):
    page.click(field)
    page.keyboard.type(pin, delay=60)
    page.keyboard.press('Enter')
    time.sleep(1.5)


def new_context(p, width, height, dsf=2, scheme='light', forced=None, reduced=None):
    browser = p.chromium.launch(headless=True)
    kwargs = dict(viewport={'width': width, 'height': height}, device_scale_factor=dsf, color_scheme=scheme)
    if forced:
        kwargs['forced_colors'] = forced
    ctx = browser.new_context(**kwargs)
    return browser, ctx


def hidden_state(page, sel):
    return page.evaluate('(s) => { const e = document.querySelector(s); return e ? e.hidden : null }', sel)
