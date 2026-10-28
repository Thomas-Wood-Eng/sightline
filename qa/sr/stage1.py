"""Stage 1: landing, heading/landmark structure, full forward Tab order, setup by keyboard."""
import sys, json; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from harness import *
with sync_playwright() as p:
    b, ctx = launch(p); page = ctx.new_page()
    run = Run('stage1'); run.mark('1 landing')
    page.goto(BASE + '/'); page.wait_for_timeout(1200)
    run.collect(page)
    # structure via accessibility tree (approximation of NVDA's H / D / F lists)
    heads = page.evaluate("() => Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.tagName + ': ' + h.textContent.trim())")
    lands = page.evaluate("() => Array.from(document.querySelectorAll('main,header,footer,nav,section,[role]')).map(e => (e.getAttribute('role')||e.tagName.toLowerCase()) + ' ' + (e.getAttribute('aria-labelledby')||'') + ' ' + (e.getAttribute('aria-label')||''))")
    print('HEADINGS', heads); print('LANDMARK-ish', lands)
    # full forward Tab order from the top of the page
    order = []
    for i in range(1, 75):
        page.keyboard.press('Tab')
        d = active(page); order.append(f'{i}: {d}')
        if 'Save and start' in d and '[button]' in d: break
    print('TAB ORDER (setup)'); print('\n'.join(order))
    run.collect(page)
    run.mark('1b setup')
    # Setup: focus is on Save button now. Fill via keyboard: shift+tab back to PIN
    for name in ['setup-pin', 'setup-pin2']:
        pass
    page.keyboard.press('Shift+Tab')  # daily cap
    page.keyboard.press('Shift+Tab')  # order cap
    page.keyboard.press('Shift+Tab')  # pin2 label? (inputs only matter)
    print('focus now', active(page))
    # go to PIN via Shift+Tab until id setup-pin
    n, d = tab_until(page, "el.id === 'setup-pin'", shift=True, max_tabs=10)
    print('reached PIN after', n, d)
    page.keyboard.type('1234'); page.keyboard.press('Tab'); page.keyboard.type('1234')
    print('after typing PINs', active(page))
    run.collect(page)
    run.mark('1c submit setup')
    page.keyboard.press('Enter') if False else None
    n, d = tab_until(page, "el.id === 'setup-status' || (el.tagName==='BUTTON' && el.textContent.includes('Save and start'))", max_tabs=10)
    print('before submit focus', d)
    page.keyboard.press('Enter') if 'Save and start' in d else None
    page.wait_for_timeout(1200)
    run.collect(page)
    print('after submit', active(page))
    run.show()
    print('SETUP SHOWN?', page.evaluate("() => document.getElementById('setup').hidden"))
    ctx.storage_state(path='C:/Projects/paypal_hackathon/qa/shots/sr/state.json')
    run.save(); b.close()
