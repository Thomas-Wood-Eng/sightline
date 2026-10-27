import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p7'
JS_ACTIVE = """() => { const e = document.activeElement; if (!e || e===document.body) return 'BODY';
  const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
  const lbl = (e.id ? '#'+e.id : e.tagName.toLowerCase()) + ' [' + (e.type||'') + '] "' + ((e.innerText||e.value||e.getAttribute('aria-label')||'').trim().slice(0,40)) + '"';
  return lbl + ' | outline=' + cs.outlineStyle + ' ' + cs.outlineWidth + ' | y=' + Math.round(r.top) + ' inView=' + (r.top>=0 && r.bottom<=innerHeight); }"""
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    order = []
    for i in range(45):
        page.keyboard.press('Tab'); time.sleep(0.05)
        order.append(page.evaluate(JS_ACTIVE))
        if i in (0, 1, 8): shot(page, f'p7_tab_{i:02d}')
    for i, o in enumerate(order): note(P, 'tab_order', f'{i+1}: {o}')
    browser.close()
