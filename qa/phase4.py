import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p4'
def focus_id(page):
    return page.evaluate('() => (document.activeElement && (document.activeElement.id || document.activeElement.tagName))')
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); page.wait_for_selector('#log .turn'); time.sleep(0.5)
    page.fill('#set-contact-name', 'Alex'); page.fill('#set-contact-email', 'alex@example.com')
    page.fill('#set-threshold', '50'); page.fill('#set-current-pin', '1234')
    page.click('#settings-form button[type=submit]'); time.sleep(1.5)
    note(P, 'contact_saved', page.inner_text('#settings-status'), shot(page, 'p4_01_contact_saved'))
    page.locator('#settings-status').scroll_into_view_if_needed(); time.sleep(0.3)
    t = send(page, 'find me a heavyweight hoodie', ai=True)
    note(P, 'search2', t[:300], shot(page, 'p4_02_search2'))
    t = send(page, 'add the second one')
    note(P, 'add2', t[:300])
    t = send(page, 'large')
    note(P, 'size_L', t[:300], shot(page, 'p4_03_added'))
    t = send(page, 'check out')
    note(P, 'readback2', t[:600], shot(page, 'p4_04_readback_over50'))
    t = send(page, 'confirm')
    note(P, 'confirm2', t[:600] + ' | pin=' + str(page.is_visible('#pin-form')), shot(page, 'p4_05_after_confirm'))
    links = page.locator('#log a').all()
    hrefs = [a.get_attribute('href') for a in links]
    note(P, 'approval_links', str(hrefs))
    ctx.storage_state(path='qa/state_p4.json')
    if hrefs:
        ap = ctx.new_page(); ap.goto(BASE + hrefs[-1]); time.sleep(0.5)
        note(P, 'approve_page', ap.inner_text('main')[:400], shot(ap, 'p4_06_approve_page'))
        ap.click('button:has-text("Approve")'); time.sleep(1)
        note(P, 'approved', ap.inner_text('main')[:200], shot(ap, 'p4_07_approved'))
        ap.close()
        time.sleep(1)
        t = send(page, 'what is the status')
        note(P, 'status_after_approval', t[:300], shot(page, 'p4_08_status'))
        page.reload(); time.sleep(1.5)
        note(P, 'after_reload_state', 'pin=' + str(page.is_visible('#pin-form')) + ' undo=' + str(page.is_visible('#undo-box')) + ' last=' + last_turn(page)[:200], shot(page, 'p4_09_reload'))
    ctx.storage_state(path='qa/state_p4.json')
    browser.close()
