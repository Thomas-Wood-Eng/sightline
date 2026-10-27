import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p6d'
def fid(page): return page.evaluate('() => document.activeElement && (document.activeElement.id || document.activeElement.tagName)')
def st(page): return page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)")
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.check('input[name=screen_reader][value=no]')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    t = send(page, 'find me a warm hoodie', ai=True)
    t = send(page, 'add the first one'); t = send(page, 'M')
    # Escape on an idle page first
    page.click('#message'); page.keyboard.press('Escape'); time.sleep(0.5)
    note(P, 'esc_idle', 'turns=' + str(turns(page)) + ' last=' + last_turn(page)[-100:].replace('\n',' '))
    t = send(page, 'check out'); t = send(page, 'confirm')
    note(P, 'pin_ready_A', 'state=' + st(page) + ' focus=' + fid(page), shot(page, 'p6d_01_pin_ready'))
    page.keyboard.press('Escape'); time.sleep(1.5)
    note(P, 'esc_at_pin_box', last_turn(page)[-220:].replace('\n',' ') + ' | state=' + st(page) + ' pin=' + str(page.is_visible('#pin-form')), shot(page, 'p6d_02_esc_pin'))
    # second checkout: zoom to 400% (320x480) while PIN box is open
    t = send(page, 'check out'); t = send(page, 'confirm')
    note(P, 'pin_ready_B', 'state=' + st(page) + ' focus=' + fid(page), shot(page, 'p6d_03_pin_ready_B_640'))
    page.set_viewport_size({'width': 320, 'height': 480}); time.sleep(0.8)
    note(P, 'zoom_400_at_pin', 'focus=' + fid(page) + ' pin=' + str(page.is_visible('#pin-form')) + ' overflow=' + str(overflow(page)), shot(page, 'p6d_04_pin_400'))
    page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(1.2)
    note(P, 'undo_400', last_turn(page)[-200:].replace('\n',' ') + ' | undo_visible=' + str(page.is_visible('#undo-box')), shot(page, 'p6d_05_undo_400'))
    time.sleep(1.0)
    spk = page.evaluate("() => ('speechSynthesis' in window) ? speechSynthesis.speaking : 'n/a'")
    note(P, 'speech_state', 'speechSynthesis.speaking=' + str(spk))
    page.keyboard.press('Escape'); time.sleep(1.5)
    note(P, 'esc_in_undo', last_turn(page)[-200:].replace('\n',' ') + ' | state=' + st(page) + ' undo=' + str(page.is_visible('#undo-box')), shot(page, 'p6d_06_esc_undo'))
    browser.close()
