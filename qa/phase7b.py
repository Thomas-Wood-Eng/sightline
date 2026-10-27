import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p7b'
def st(page): return page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)")
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')   # screen-reader radio left at its default "Yes"
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    t = send(page, 'something nice for my granddaughter', ai=True)
    note(P, 'vague', t[:400].replace('\n',' | '), shot(page, 'p7b_01_vague'))
    t = send(page, 'find me a hodie', ai=True)
    note(P, 'typo', t[:400].replace('\n',' | '), shot(page, 'p7b_02_typo'))
    t = send(page, 'find me a warm hoodie', ai=True)
    t = send(page, 'add the first one'); t = send(page, 'L')
    t = send(page, 'check out'); t = send(page, 'confirm')
    note(P, 'pin_ready_screenreader', 'state=' + st(page) + ' focus=' + page.evaluate('document.activeElement.id'), None)
    page.click('#pin'); page.keyboard.type('1111'); page.keyboard.press('Enter'); time.sleep(1.2)
    page.keyboard.type('2222'); page.keyboard.press('Enter'); time.sleep(1.2)
    page.keyboard.type('3333'); page.keyboard.press('Enter'); time.sleep(1.5)
    note(P, 'third_wrong', last_turn(page)[-300:].replace('\n',' | ') + ' | state=' + st(page) + ' pin=' + str(page.is_visible('#pin-form')), shot(page, 'p7b_03_locked'))
    t = send(page, 'check out')
    note(P, 'checkout_after_lock', t[-250:].replace('\n',' | '))
    time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    note(P, 'after_lock_view', 'lock', shot(page, 'p7b_04_locked_top'))
    browser.close()
