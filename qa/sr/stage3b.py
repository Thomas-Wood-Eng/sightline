import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage3b')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    send_cmd(page, run, 'check out', pace=1)
    send_cmd(page, run, 'confirm', pace=1)
    run.mark('3c PIN then wait for capture (no Escape)')
    before = turns(page)
    page.keyboard.type('1234', delay=30); page.keyboard.press('Enter')
    wait_reply(page, before)
    run.collect(page)
    # Dev keeps focus in message box; count Tab presses to reach the Undo button during the window
    tabs = []
    for i in range(1, 6):
        page.keyboard.press('Tab'); tabs.append(f'{i}: {active(page)}')
    print('TABS during undo window:'); print('\n'.join(tabs))
    run.collect(page)
    # wait out the window with no key presses, sampling focus and events
    for _ in range(14):
        time.sleep(1); run.collect(page)
    print('countdown now:', page.evaluate("() => document.getElementById('countdown').textContent"))
    last = page.evaluate("() => { const t = document.querySelectorAll('#log .turn'); return t[t.length-1].innerText; }")
    print('LAST REPLY:', last.replace('\n',' / '))
    print('pay-status:', page.evaluate("() => document.getElementById('pay-status').textContent"))
    print('undo-box hidden:', page.evaluate("() => document.getElementById('undo-box').hidden"))
    ctx.storage_state(path=STATE); run.save(); b.close()
