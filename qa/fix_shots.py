"""After the fixes: screenshots at 320 px (about 400% zoom), 1920 px, and forced colours. Usage: python qa/fix_shots.py [port]"""
import os, sys, time
from playwright.sync_api import sync_playwright
BASE = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else 8791}"
SHOTS = os.path.join(os.path.dirname(__file__), 'shots')


def send(page, text):
    n = page.locator('#log .turn').count()
    page.fill('#message', text); page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=60000)


def run(p, name, width, height, large=False, forced=False, pay=False):
    b = p.chromium.launch()
    page = b.new_page(viewport={'width': width, 'height': height}, device_scale_factor=2 if width <= 640 else 1,
                      forced_colors='active' if forced else 'none')
    page.goto(BASE); page.wait_for_selector('#log .turn')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234'); page.click('text=Save and start')
    page.wait_for_selector('#setup', state='hidden')
    if large:
        page.check('input[name=large_text]'); page.click('text=Save settings'); time.sleep(0.5)
    for t in ['help', 'find me a warm hoodie', 'tell me about the first one', 'help', 'help', 'what is in my cart']:
        send(page, t)
    page.evaluate('scrollTo(0, 0)'); page.focus('#message')
    y = page.evaluate("Math.round(document.getElementById('message').getBoundingClientRect().top + scrollY)")
    ov = page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    page.locator('#message').scroll_into_view_if_needed()
    page.screenshot(path=os.path.join(SHOTS, f'fix_{name}_log.png'))
    print(name, 'message box top', y, 'horizontal overflow', ov, flush=True)
    if pay:
        send(page, 'add the first one in medium'); send(page, 'check out'); send(page, 'confirm')
        page.wait_for_selector('#pin-form', state='visible')
        print(name, 'focus', page.evaluate('document.activeElement.id'), 'pin box:', page.inner_text('#pin-amount'), flush=True)
        page.locator('#pin-form').scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(SHOTS, f'fix_{name}_pin.png'))
        page.fill('#pin', '1234'); page.press('#pin', 'Enter'); page.wait_for_selector('#undo-box', state='visible')
        time.sleep(1.2); page.locator('#undo-box').scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(SHOTS, f'fix_{name}_undo.png'))
        print(name, 'undo box:', page.inner_text('#undo-box').replace('\n', ' | '), flush=True)
        page.keyboard.press('Escape')
        page.wait_for_function("document.getElementById('countdown').textContent.startsWith('Undone')", timeout=30000)
        page.screenshot(path=os.path.join(SHOTS, f'fix_{name}_undone.png'))
        print(name, 'after Escape:', page.inner_text('#countdown'), flush=True)
    b.close()


with sync_playwright() as p:
    run(p, '320_large', 320, 480, large=True, pay=True)   # ~400% zoom reflow, large text
    run(p, '1920', 1920, 1080)
    run(p, '320_forced', 320, 480, forced=True, pay=True)
