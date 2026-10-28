import sys, time, json; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(storage_state=STATE); page = ctx.new_page()
    page.goto(BASE + '/'); page.wait_for_timeout(600)
    s = page.evaluate("async () => (await fetch('/api/settings')).json()")
    print('server state:', s['state'], s['due_in'], s['pay'], '| spent_today', s['spent_today'])
    print('visible log tail:', page.evaluate("() => { const t=document.querySelectorAll('#log .turn'); return t.length? t[t.length-1].innerText : '' }"))
    b.close()
