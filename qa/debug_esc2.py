import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.on('console', lambda m: print('CONSOLE', m.text, flush=True))
    page.on('response', lambda r: print('RESP', r.request.method, r.url[-12:], r.status, flush=True) if '/api/' in r.url else None)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    send(page, 'find me a warm hoodie', ai=True); send(page, 'add the first one'); send(page, 'L')
    send(page, 'check out'); send(page, 'confirm')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(0.4)
    print('JS state', page.evaluate('() => [state, busy, document.activeElement.id, speechSynthesis.speaking]'), flush=True)
    page.evaluate("() => document.addEventListener('keydown', e => console.log('KD', e.key, 'state=' + state, 'busy=' + busy), true)")
    page.keyboard.press('Escape'); time.sleep(1.0)
    print('after esc', page.evaluate('() => [state, busy]'), flush=True)
    browser.close()
