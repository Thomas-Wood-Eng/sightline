import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'drift'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    def pos(tag):
        y = page.evaluate("() => Math.round(document.getElementById('message').getBoundingClientRect().top + scrollY)")
        note(P, tag, f'message box top (page px)={y}, turns={turns(page)}')
    pos('start')
    for i in range(6):
        send(page, 'help')
    pos('after 6 help replies')
    send(page, 'help'); send(page, 'help'); send(page, 'help'); send(page, 'help')
    pos('after 10 help replies')
    shot(page, 'drift_after10')
    browser.close()
