import sys, time, json; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
def srv(page): return page.evaluate("async () => { const s = await (await fetch('/api/settings')).json(); return [s.state, s.due_in, s.pay]; }")
def turns_text(page):
    raw = page.evaluate("() => Array.from(document.querySelectorAll('#log .turn')).slice(-3).map(x => x.innerText)")
    return [r.replace(chr(10), ' / ')[:300] for r in raw]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage6d')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    print('SERVER before reload:', srv(page))
    print('DOUBLE check-out, last turns in log:')
    for t in turns_text(page)[-2:]: print('  ', t)
    run.mark('6j reload mid-checkout')
    page.reload(); page.wait_for_timeout(1200); run.collect(page)
    print('AFTER RELOAD focus:', active(page)[:100])
    print('AFTER RELOAD log:', page.evaluate("() => document.getElementById('log').innerText.slice(0,140)"))
    print('SERVER after reload:', srv(page), '| pin-form hidden:', page.evaluate("() => document.getElementById('pin-form').hidden"))
    ctx.storage_state(path=STATE); run.save(); b.close()
