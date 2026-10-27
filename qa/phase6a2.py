import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p6a2'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p6a.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    t = send(page, 'my orders')
    note(P, 'orders_after_return', t[:300], shot(page, 'p6a2_01_orders'))
    t = send(page, 'what is in my cart')
    note(P, 'cart_while_pin', t[:200] + ' | pin=' + str(page.is_visible('#pin-form')))
    t = send(page, 'return the hoodie')
    note(P, 'return_again', t[:300])
    browser.close()
