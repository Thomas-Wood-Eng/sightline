import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
TOKEN = 'IkNCYS00ZF90TThyVG5Mb0NVUEdJQmci.t0oL2QHmTZ-rtqy1Y-C49ZMNQGA'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage5b')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    print('turns after reload:', turns(page), '| log text:', page.evaluate("() => document.getElementById('log').innerText.slice(0,160)"))
    run.mark('5d approval page')
    ap = ctx.new_page(); ap.goto(BASE + '/approve/' + TOKEN); ap.bring_to_front(); ap.wait_for_timeout(500)
    order = []
    for i in range(1, 30):
        ap.keyboard.press('Tab')
        d = ap.evaluate("() => { const e = document.activeElement; return e.tagName + ' ' + (e.textContent||e.value||'').trim().slice(0,60); }")
        order.append(str(i) + ': ' + d)
        if 'Decline' in d: break
    print('APPROVAL TAB ORDER:'); print('\n'.join(order))
    print('headings:', ap.evaluate("() => Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.textContent.trim())"))
    ctx.storage_state(path=STATE); run.save(); b.close()
