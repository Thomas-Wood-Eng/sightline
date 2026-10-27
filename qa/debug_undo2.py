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
    page.on('response', lambda r: logs.append(('resp', r.request.method, r.url, r.status)) if '/api/' in r.url else None)
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(2)
    print('undo box', page.is_visible('#undo-box'), 'turns', turns(page), last_turn(page)[:150])
    print('finalize ->', page.evaluate("fetch('/api/finalize',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.text())"))
    for l in logs: print(l)
    browser.close()
