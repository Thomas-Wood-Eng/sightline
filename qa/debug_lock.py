import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def fid(page): return page.evaluate('() => document.activeElement && (document.activeElement.id || document.activeElement.tagName)')
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    send(page, 'find me a warm hoodie', ai=True); send(page, 'add the first one'); send(page, 'L')
    send(page, 'check out'); send(page, 'confirm')
    for pin in ['1111', '2222', '3333']:
        print('focus before', fid(page), 'pinvis', page.is_visible('#pin-form'), flush=True)
        page.keyboard.type(pin); page.keyboard.press('Enter'); time.sleep(2)
        print(pin, '->', last_turn(page)[-90:].replace('\n',' '), '| turns', turns(page), flush=True)
    shot(page, 'dbg_lock')
    browser.close()
