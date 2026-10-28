import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage5')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    for t in ['headphones', 'next', 'add it']:
        send_cmd(page, run, t, pace=16)
    run.mark('5a checkout over threshold')
    send_cmd(page, run, 'check out', pace=2)
    send_cmd(page, run, 'confirm', pace=2)
    run.mark('5b PIN, approval needed')
    before = turns(page)
    page.keyboard.type('1234'); page.keyboard.press('Enter')
    try: wait_reply(page, before)
    except Exception as e: print('timeout', e)
    run.collect(page)
    last = page.evaluate("() => { const t = document.querySelectorAll('#log .turn'); return t[t.length-1].innerText; }")
    print('APPROVAL REPLY:', last.replace('\n',' / '))
    print('focus:', active(page)[:140])
    # keyboard path to the approval link (Dev tabs into the log, then Enter)
    tab_to_link = tab_until(page, "el.tagName==='A' && el.href.includes('/approve/')", max_tabs=40)
    print('tabs to approval link:', tab_to_link)
    run.mark('5c open approval page via keyboard')
    try:
        with ctx.expect_page(timeout=8000) as newp_info:
            page.keyboard.press('Enter')
        ap = newp_info.value
        ap.wait_for_load_state()
        print('approval tab title:', ap.title(), '| url:', ap.url)
        print('approval text:', ap.evaluate("() => document.body.innerText").replace('\n',' / ')[:600])
        ap.bring_to_front()
        for i in range(1, 12):
            ap.keyboard.press('Tab')
        print('approval tab after 12 tabs:', ap.evaluate("() => document.activeElement.outerHTML.slice(0,160)"))
        ap.screenshot(path='C:/Projects/paypal_hackathon/qa/shots/sr/approval.png')
    except Exception as e:
        print('approval open problem:', e)
    ctx.storage_state(path=STATE); run.save(); b.close()
