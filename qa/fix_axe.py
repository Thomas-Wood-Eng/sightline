"""axe-core (WCAG 2.2 A/AA + best practice) on the main page in its main states: after setup, PIN box, undo box.
Usage: python qa/fix_axe.py [port]"""
import json, sys, time
from playwright.sync_api import sync_playwright
BASE = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else 8791}"
AXE = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js'


def send(page, text):
    n = page.locator('#log .turn').count()
    page.fill('#message', text); page.press('#message', 'Enter')
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=60000)


def axe(page, label):
    page.add_script_tag(url=AXE)
    r = page.evaluate("axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']})")
    v = [(x['id'], x['impact'], len(x['nodes'])) for x in r['violations']]
    print(f'{label}: {len(v)} violations {v}', flush=True)
    return len(v)


total = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ('light', 'dark'):
        page = b.new_page(viewport={'width': 1280, 'height': 900}, color_scheme=scheme)
        page.goto(BASE); page.wait_for_selector('#log .turn')
        total += axe(page, f'{scheme} setup form')
        page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234'); page.click('text=Save and start')
        page.wait_for_selector('#setup', state='hidden')
        send(page, 'hoodie'); send(page, 'add number 1 in M'); send(page, 'check out'); send(page, 'confirm')
        page.wait_for_selector('#pin-form', state='visible')
        total += axe(page, f'{scheme} PIN box')
        page.fill('#pin', '1234'); page.press('#pin', 'Enter'); page.wait_for_selector('#undo-box', state='visible')
        total += axe(page, f'{scheme} undo box')
        page.keyboard.press('Escape')
        page.wait_for_function("document.getElementById('countdown').textContent.startsWith('Undone')", timeout=30000)
        total += axe(page, f'{scheme} after undo')
        page.close()
    b.close()
print('TOTAL violations', total)
