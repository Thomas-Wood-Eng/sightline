import sys, time, json, base64, zlib
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def dec(v):
    payload = v.split('.')[0].lstrip('.')
    raw = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))
    if raw[:1] == b'.': raw = zlib.decompress(raw[1:])
    return json.loads(raw)
def show(ctx, tag):
    c = [x for x in ctx.cookies() if x['name']=='session'][0]['value']
    d = dec(c)
    print(tag, 'len', len(c), 'contact', d.get('contact'), 'state', d.get('co',{}).get('state'), 'keys', len(d), flush=True)
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    show(ctx, 'loaded')
    page.fill('#set-contact-name', 'Alex'); page.fill('#set-contact-email', 'alex@example.com')
    page.fill('#set-threshold', '50'); page.fill('#set-current-pin', '1234')
    page.click('#settings-form button[type=submit]'); time.sleep(1.5)
    show(ctx, 'saved')
    send(page, 'check out'); show(ctx, 'checkout')
    browser.close()
