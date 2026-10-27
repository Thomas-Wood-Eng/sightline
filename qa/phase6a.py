import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p6a'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p5.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    t = send(page, 'how much did I spend this week')
    note(P, 'spend', t[:300], shot(page, 'p6a_01_spend'))
    t = send(page, 'my orders')
    note(P, 'orders', t[:500], shot(page, 'p6a_02_orders'))
    t = send(page, 'return the hoodie')
    note(P, 'return_readback', t[:500], shot(page, 'p6a_03_return_readback'))
    t = send(page, 'confirm')
    note(P, 'return_confirm', t[:300] + ' | pin=' + str(page.is_visible('#pin-form')), shot(page, 'p6a_04_return_pin'))
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(4)
    note(P, 'return_done', last_turn(page)[:400] + ' | undo=' + str(page.is_visible('#undo-box')), shot(page, 'p6a_05_return_done'))
    ctx.storage_state(path='qa/state_p6a.json')
    browser.close()
