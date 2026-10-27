import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.check('input[name=screen_reader][value=no]')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    for s in ['find me a warm hoodie', 'add it', 'M', 'check out', 'confirm']:
        t = send(page, s, ai=(s.startswith('find')))
        print('>>', s, '::', t.replace('\n', ' | ')[:260], flush=True)
    browser.close()
