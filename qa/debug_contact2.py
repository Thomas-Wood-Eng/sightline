import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def show(page, tag):
    print(tag, page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>JSON.stringify(j.contact))"), flush=True)
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#set-contact-name', 'Alex'); page.fill('#set-contact-email', 'alex@example.com')
    page.fill('#set-threshold', '50'); page.fill('#set-current-pin', '1234')
    page.click('#settings-form button[type=submit]'); time.sleep(1.5)
    print(page.inner_text('#settings-status'))
    show(page, 'after save')
    send(page, 'check out'); show(page, 'after checkout'); 
    send(page, 'cancel'); show(page, 'after cancel')
    browser.close()
