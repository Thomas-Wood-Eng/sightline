import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p4b.json'))['cookies'])
    page = ctx.new_page()
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn')
    print('loaded undo_box', page.is_visible('#undo-box'), 'last:', last_turn(page)[:80], flush=True)
    # finalize fires ~0.3s after load and takes a few seconds (PayPal capture). Save a trusted contact while it runs.
    time.sleep(1.0); t0 = time.time()
    res = page.evaluate("""async () => {
      const save = fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({contact_name:'Alex', contact_email:'alex@example.com', approval_threshold:'50', current_pin:'1234'})}).then(r=>r.status);
      const sres = await save;
      return sres;
    }""")
    print('settings save status', res, 'after', round(time.time()-t0,2), flush=True)
    time.sleep(6)
    print('contact now:', page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>JSON.stringify(j.contact))"))
    print('undo box', page.is_visible('#undo-box'), 'last:', last_turn(page)[:120], flush=True)
    browser.close()
