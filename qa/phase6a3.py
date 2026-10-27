import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p6a3'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p6a.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    t = send(page, 'cancel')
    note(P, 'cancel_after_refund_in_db', t[:300])
    t = send(page, 'my orders')
    note(P, 'orders_after', t[:300], shot(page, 'p6a3_01_orders'))
    browser.close()
