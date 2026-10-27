import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p4b.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); time.sleep(1)
    print(page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>JSON.stringify({c:j.contact,s:j.state,t:j.spent_today}))"))
    print([ (c['name'], len(c['value'])) for c in json.load(open('qa/state_p4b.json'))['cookies']])
    browser.close()
