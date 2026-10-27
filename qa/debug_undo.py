import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page()
    logs = []
    page.on('console', lambda m: logs.append(('console', m.type, m.text)))
    page.on('pageerror', lambda e: logs.append(('pageerror', str(e))))
    page.on('requestfinished', lambda r: logs.append(('req', r.method, r.url, r.response().status if r.response() else None)) if '/api/' in r.url else None)
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    print('state at load', page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)"))
    send(page, 'check out'); send(page, 'confirm')
    page.click('#pin'); page.keyboard.type('1234'); page.keyboard.press('Enter')
    t0 = time.time()
    for i in range(14):
        time.sleep(1)
        print(round(time.time()-t0), 'turns', turns(page), 'undo', page.is_visible('#undo-box'), 'pinform', page.is_visible('#pin-form'))
    print(last_turn(page)[:200])
    for l in logs: print(l)
    browser.close()
