import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p4b'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p4.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    t = send(page, 'cancel')
    note(P, 'cancel_pin', t[:200] + ' | pin=' + str(page.is_visible('#pin-form')))
    t = send(page, 'find me a heavyweight hoodie', ai=True)
    note(P, 'search3', t[:200])
    t = send(page, 'add the first one')
    t = send(page, 'XL')
    note(P, 'added_xl', t[:200])
    t = send(page, 'what is in my cart')
    note(P, 'cart', t[:300], shot(page, 'p4b_01_cart'))
    t = send(page, 'check out')
    note(P, 'readback_big', t[:700], shot(page, 'p4b_02_readback_big'))
    t = send(page, 'confirm')
    note(P, 'confirm_big', t[:700] + ' | pin=' + str(page.is_visible('#pin-form')), shot(page, 'p4b_03_after_confirm'))
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(2)
    note(P, 'pin_big', last_turn(page)[:700] + ' | pin=' + str(page.is_visible('#pin-form')) + ' undo=' + str(page.is_visible('#undo-box')), shot(page, 'p4b_04_after_pin_big'))
    links = [a.get_attribute('href') for a in page.locator('#log a').all()]
    note(P, 'approval_links', str(links))
    if links:
        ap = ctx.new_page(); ap.goto(BASE + links[-1]); time.sleep(0.5)
        note(P, 'approve_page', ap.inner_text('main')[:500], shot(ap, 'p4b_05_approve_page'))
        ap.click('button:has-text("Approve")'); time.sleep(1)
        note(P, 'approved', ap.inner_text('main')[:200], shot(ap, 'p4b_06_approved'))
        ap.close()
    time.sleep(2)
    note(P, 'after_approval', 'undo=' + str(page.is_visible('#undo-box')) + ' pin=' + str(page.is_visible('#pin-form')) + ' last=' + last_turn(page)[:300], shot(page, 'p4b_07_after_approval'))
    ctx.storage_state(path='qa/state_p4b.json')
    browser.close()
