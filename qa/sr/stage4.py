import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
def tab_to(page, pred, label, shift=False, maxn=120):
    n, d = tab_until(page, pred, max_tabs=maxn, shift=shift)
    print(f'{label}: tabs={n} -> {d}'); return n
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage4')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    # --- Settings: verbosity brief (keyboard: Tab to the radio, Space) ---
    run.mark('4a settings brief')
    tab_to(page, "el.name==='verbosity' && el.value==='brief'", 'brief radio')
    page.keyboard.press('Space')
    run.collect(page)
    tab_to(page, "el.id==='set-current-pin'", 'current PIN field')
    tab_to(page, "el.tagName==='BUTTON' && el.textContent.includes('Save settings')", 'Save settings button')
    page.keyboard.press('Enter'); page.wait_for_timeout(1200); run.collect(page)
    print('settings-status:', page.evaluate("() => document.getElementById('settings-status').textContent"))
    print('focus after save:', active(page))
    # --- wrong current PIN on trusted-contact save ---
    run.mark('4b wrong PIN')
    tab_to(page, "el.id==='set-contact-name'", 'contact name')
    page.keyboard.type('Sam Test'); 
    tab_to(page, "el.id==='set-contact-email'", 'contact email'); page.keyboard.type('sam@example.com')
    tab_to(page, "el.id==='set-threshold'", 'threshold'); page.keyboard.type('50')
    tab_to(page, "el.id==='set-current-pin'", 'current PIN'); page.keyboard.type('9999')
    tab_to(page, "el.tagName==='BUTTON' && el.textContent.includes('Save settings')", 'save')
    page.keyboard.press('Enter'); page.wait_for_timeout(1200); run.collect(page)
    print('settings-status after wrong PIN:', page.evaluate("() => document.getElementById('settings-status').textContent"))
    print('focus after wrong PIN:', active(page))
    # --- correct PIN ---
    run.mark('4c contact save')
    tab_to(page, "el.id==='set-current-pin'", 'current PIN again')
    page.keyboard.type('1234')
    tab_to(page, "el.tagName==='BUTTON' && el.textContent.includes('Save settings')", 'save again')
    page.keyboard.press('Enter'); page.wait_for_timeout(1500); run.collect(page)
    print('settings-status after correct PIN:', page.evaluate("() => document.getElementById('settings-status').textContent"))
    ctx.storage_state(path=STATE); run.save(); b.close()
