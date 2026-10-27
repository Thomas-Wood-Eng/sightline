import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open(sys.argv[1]))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(3)
    print('state', page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state+' spent='+j.spent_today)"))
    print('last turn:', last_turn(page)[-300:])
    print('pin', page.is_visible('#pin-form'), 'undo', page.is_visible('#undo-box'))
    browser.close()
