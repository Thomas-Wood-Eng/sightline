"""Live re-run of debug_race.py after the fix: save a trusted contact while the page's finalize call is
capturing on PayPal, then check the contact is kept and the next order over the threshold needs approval.
(The old state_p4b.json cookie no longer works: cookies now carry only a session id.)"""
import sys, time
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
    page.click('button:has-text("Save and start")'); time.sleep(1.5)
    send(page, 'hoodie'); send(page, 'add number 1 in M'); send(page, 'check out'); send(page, 'confirm')
    page.fill('#pin', '1234'); page.press('#pin', 'Enter'); page.wait_for_selector('#undo-box', state='visible')
    page.wait_for_function("document.getElementById('countdown').textContent === 'Paying now…'", timeout=20000)
    time.sleep(0.5); t0 = time.time()  # the capture is in flight now
    res = page.evaluate("""() => fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({contact_name:'Alex', contact_email:'alex@example.com', approval_threshold:'20', current_pin:'1234'})}).then(r=>r.status)""")
    print('settings save status', res, 'took', round(time.time() - t0, 2), 's (waited for the capture)', flush=True)
    page.wait_for_function("document.getElementById('countdown').textContent.startsWith('Paid')", timeout=20000)
    print('result box:', page.inner_text('#countdown')[:60], flush=True)
    time.sleep(2)
    print('contact now:', page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>JSON.stringify(j.contact))"), flush=True)
    send(page, 'hoodie'); send(page, 'add number 1 in M')
    print('check out ->', send(page, 'check out').replace('\n', ' | ')[-260:], flush=True)
    send(page, 'cancel')
    browser.close()
