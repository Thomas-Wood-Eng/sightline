import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
def tab_to(page, pred, label, shift=False, maxn=120):
    n, d = tab_until(page, pred, max_tabs=maxn, shift=shift)
    print(f'{label}: tabs={n} -> {d[:110]}'); return n
def settings_save(page, run, label):
    tab_to(page, "el.tagName==='BUTTON' && el.textContent.includes('Save settings')", label)
    page.keyboard.press('Enter'); page.wait_for_timeout(1500); run.collect(page)
    print('  settings-status:', page.evaluate("() => document.getElementById('settings-status').textContent"))
    print('  focus:', active(page)[:120])
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage4b')
    page.goto(BASE + '/'); page.wait_for_timeout(800); run.collect(page)
    # raw server answer for the wrong PIN (second attempt), for the record
    raw = page.evaluate("""async () => { const r = await fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({current_pin:'9999', verbosity:'brief', simple_mode:false, large_text:false, default_size:'', avoid_allergens:'', contact_name:'', contact_email:'', approval_threshold:'', output_mode:null, per_order_cap:null, daily_cap:null, new_pin:null})}); return [r.status, await r.text()]; }""")
    print('RAW wrong-PIN response:', raw)
    # Dev: radio group, Tab lands on the checked radio only; arrows change it
    tab_to(page, "el.name==='verbosity' && el.checked", 'verbosity group (checked radio)')
    page.keyboard.press('ArrowUp'); page.keyboard.press('ArrowUp')  # normal -> brief
    print('after arrows:', active(page)[:120]); run.collect(page)
    tab_to(page, "el.id==='set-current-pin'", 'current PIN'); page.keyboard.press('Control+A'); page.keyboard.type('1234')
    settings_save(page, run, 'save (brief)')
    run.mark('4d back to normal')
    tab_to(page, "el.name==='verbosity' && el.checked", 'verbosity checked (brief)')
    page.keyboard.press('ArrowDown'); run.collect(page)
    tab_to(page, "el.id==='set-current-pin'", 'current PIN'); page.keyboard.press('Control+A'); page.keyboard.type('1234')
    settings_save(page, run, 'save (normal)')
    run.mark('4e trusted contact')
    tab_to(page, "el.id==='set-contact-name'", 'contact name')
    page.keyboard.press('Control+A'); page.keyboard.type('Sam Test')
    tab_to(page, "el.id==='set-contact-email'", 'contact email'); page.keyboard.type('sam@example.com')
    tab_to(page, "el.id==='set-threshold'", 'threshold'); page.keyboard.press('Control+A'); page.keyboard.type('50')
    tab_to(page, "el.id==='set-current-pin'", 'current PIN'); page.keyboard.press('Control+A'); page.keyboard.type('1234')
    settings_save(page, run, 'save contact')
    ctx.storage_state(path=STATE); run.save(); b.close()
