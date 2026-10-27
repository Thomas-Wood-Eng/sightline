import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p3'
def focus_id(page):
    return page.evaluate('() => (document.activeElement && (document.activeElement.id || document.activeElement.tagName))')
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    # NOTE: reuse the session cookie from phase 2
    ctx.add_cookies(json.load(open('qa/state_p2.json'))['cookies'])
    page = ctx.new_page()
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    note(P, 'resume', 'focus=' + focus_id(page) + ' setup_visible=' + str(page.is_visible('#setup')))
    t = send(page, 'check out')
    note(P, 'checkout_readback', t[:700], shot(page, 'p3_01_readback'))
    t = send(page, 'confirm')
    note(P, 'after_confirm', t[:300] + ' | pinform_visible=' + str(page.is_visible('#pin-form')) + ' focus=' + focus_id(page), shot(page, 'p3_02_pin_box'))
    page.locator('#pin-form').scroll_into_view_if_needed(); time.sleep(0.3)
    note(P, 'pin_box_view', 'pin form in view', shot(page, 'p3_03_pin_box_view'))
    # Maria types the PIN into the PIN box
    page.keyboard.type('1234', delay=80)
    page.keyboard.press('Enter'); time.sleep(1.5)
    note(P, 'pin_entered', last_turn(page)[:300] + ' | undo_visible=' + str(page.is_visible('#undo-box')), shot(page, 'p3_04_undo_window'))
    time.sleep(3)
    note(P, 'undo_countdown_visible', 'undo box at +3s: ' + str(page.is_visible('#undo-box')) + ' text=' + page.inner_text('#undo-box'), shot(page, 'p3_05_undo_3s'))
    t = send(page, 'undo', wait=1.0)
    note(P, 'undo_typed', t[:300] + ' | undo_box=' + str(page.is_visible('#undo-box')), shot(page, 'p3_06_after_undo'))
    # check out again and let it pay
    t = send(page, 'check out')
    t = send(page, 'confirm')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(0.5)
    note(P, 'second_pin', 'waiting 12s', None)
    time.sleep(12)
    note(P, 'after_wait', last_turn(page)[:500] + ' | undo_box=' + str(page.is_visible('#undo-box')), shot(page, 'p3_07_paid'))
    ctx.storage_state(path='qa/state_p3.json')
    browser.close()
