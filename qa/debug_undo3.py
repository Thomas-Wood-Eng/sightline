import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page()
    page.on('response', lambda r: print('RESP', r.request.method, r.url, r.status, r.text()[:160]) if '/api/' in r.url else None)
    page.on('pageerror', lambda e: print('PAGEERR', e))
    page.add_init_script("""window.__t0=Date.now(); const _st=window.setTimeout; window.setTimeout=function(f,d,...a){ if(d>=250 && d<=2000) console.log('timer', d, Date.now()-window.__t0); return _st.call(window,f,d,...a)};""")
    page.on('console', lambda m: print('CONSOLE', m.text))
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn')
    for i in range(6):
        time.sleep(1); print(i+1, 'turns', turns(page), 'undo', page.is_visible('#undo-box'))
    browser.close()
