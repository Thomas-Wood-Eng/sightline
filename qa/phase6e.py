import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p6e'
def st(page): return page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)")
def spk(page): return page.evaluate("() => speechSynthesis.speaking")
def reach_pin(page, tag):
    send(page, 'check out'); send(page, 'confirm')
    time.sleep(0.5)
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.check('input[name=screen_reader][value=no]')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    send(page, 'find me a warm hoodie', ai=True); send(page, 'add the first one'); send(page, 'M')
    send(page, 'check out'); send(page, 'confirm')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter')
    time.sleep(0.4)
    note(P, 'voice_mode_undo_start', 'state=' + st(page) + ' speaking=' + str(spk(page)) + ' undo=' + str(page.is_visible('#undo-box')), shot(page, 'p6e_01_voice_undo_start'))
    page.keyboard.press('Escape'); time.sleep(0.6)
    note(P, 'voice_mode_esc1', 'state=' + st(page) + ' speaking=' + str(spk(page)) + ' undo=' + str(page.is_visible('#undo-box')) + ' last=' + last_turn(page)[-90:].replace('\n',' '), shot(page, 'p6e_02_voice_esc1'))
    time.sleep(3)
    note(P, 'voice_mode_after_3s', 'state=' + st(page) + ' speaking=' + str(spk(page)) + ' undo=' + str(page.is_visible('#undo-box')), None)
    page.keyboard.press('Escape'); time.sleep(1.0)
    note(P, 'voice_mode_esc2', 'state=' + st(page) + ' undo=' + str(page.is_visible('#undo-box')) + ' last=' + last_turn(page)[-140:].replace('\n',' '), shot(page, 'p6e_03_voice_esc2'))
    browser.close()
