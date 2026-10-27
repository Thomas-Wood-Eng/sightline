import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def st(page): return page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)")
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    send(page, 'find me a warm hoodie', ai=True); send(page, 'add the first one'); send(page, 'L')
    send(page, 'check out'); send(page, 'confirm')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter'); time.sleep(0.4)
    t0 = time.time()
    page.keyboard.press('Escape')
    for i in range(12):
        time.sleep(1)
        print(round(time.time()-t0,1), 'busy', page.evaluate('() => busy'), 'last', last_turn(page)[-50:].replace('\n',' '), flush=True)
        if not page.evaluate('() => busy') and 'Undone' in last_turn(page): break
    print('server state', st(page), flush=True)
    browser.close()
