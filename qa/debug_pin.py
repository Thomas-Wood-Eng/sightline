import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def fid(page): return page.evaluate('() => document.activeElement && (document.activeElement.id || document.activeElement.tagName)')
def st(page): return page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>j.state)")
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p6a.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    print('start', st(page), fid(page), flush=True)
    t = send(page, 'find me a warm hoodie', ai=True); print('search', t[-80:].replace('\n',' '), flush=True)
    t = send(page, 'add it'); print('add', t[-80:].replace('\n',' '), fid(page), flush=True)
    t = send(page, 'M'); print('size', t[-80:].replace('\n',' '), flush=True)
    t = send(page, 'check out'); print('co', st(page), fid(page), flush=True)
    t = send(page, 'confirm'); print('confirm', st(page), 'focus', fid(page), 'pinvis', page.is_visible('#pin-form'), flush=True)
    time.sleep(1); print('+1s focus', fid(page), flush=True)
    shot(page, 'dbg_pin_ready')
    browser.close()
