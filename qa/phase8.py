import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def run(p, tag, w, h, scheme, forced=None, large=False):
    browser = p.chromium.launch(headless=True)
    kw = dict(viewport={'width': w, 'height': h}, device_scale_factor=2, color_scheme=scheme)
    if forced: kw['forced_colors'] = forced
    ctx = browser.new_context(**kw)
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    shot(page, f'{tag}_00_load')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    if large:
        page.click('label:has-text("Large text")'); page.click('button:has-text("Save settings")'); time.sleep(1.5)
    send(page, 'find me a warm hoodie', ai=True)
    shot(page, f'{tag}_01_results')
    note(tag, 'results_overflow', str(overflow(page)))
    send(page, 'add the first one'); send(page, 'M')
    send(page, 'check out'); send(page, 'confirm')
    time.sleep(0.5)
    # Readback total: scroll the total line into view
    page.evaluate("() => { const t=[...document.querySelectorAll('.total')].pop(); if (t) t.scrollIntoView({block:'center'}); }")
    time.sleep(0.4); shot(page, f'{tag}_02_total')
    note(tag, 'total_overflow', str(overflow(page)))
    page.evaluate("() => document.getElementById('pin-form').scrollIntoView({block:'center'})"); time.sleep(0.4)
    shot(page, f'{tag}_03_pin_box')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(1.2)
    note(tag, 'undo_box', 'visible=' + str(page.is_visible('#undo-box')), None)
    page.evaluate("() => document.getElementById('undo-box').scrollIntoView({block:'center'})"); time.sleep(0.4)
    shot(page, f'{tag}_04_undo')
    time.sleep(12)
    note(tag, 'after_capture', last_turn(page)[-160:].replace('\n',' '))
    browser.close()
mode = sys.argv[1]
with sync_playwright() as p:
    if mode == 'big':
        run(p, 'p8big', 320, 480, 'light', large=True)
    elif mode == 'dark':
        run(p, 'p8dark', 640, 360, 'dark')
    elif mode == 'forced':
        run(p, 'p8forced', 640, 360, 'light', forced='active')
