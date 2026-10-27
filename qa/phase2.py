import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
P = 'p2'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page()
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn')
    time.sleep(0.5)
    if page.is_visible('#setup'):
        page.check('input[name=screen_reader][value=no]')
        page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234')
        page.click('button:has-text("Save and start")'); time.sleep(1.5)
    page.click('label:has-text("Large text")'); page.click('button:has-text("Save settings")'); time.sleep(1.5)
    note(P, 'settings', 'large text on', None)
    t = send(page, 'find me a warm hoodie')
    note(P, 'search', t[:400], shot(page, 'p2_01_search_640'))
    note(P, 'search_overflow', str(overflow(page)))
    page.locator('#log').scroll_into_view_if_needed()
    t = send(page, 'tell me about the first one')
    note(P, 'describe', t[:400], shot(page, 'p2_02_describe'))
    t = send(page, 'what do people say about it', ai=True)
    note(P, 'reviews', t[:500], shot(page, 'p2_03_reviews'))
    t = send(page, 'add it')
    note(P, 'add_it', t[:300], shot(page, 'p2_04_add_it'))
    t = send(page, 'medium')
    note(P, 'size', t[:300], shot(page, 'p2_05_size'))
    ctx.storage_state(path='qa/state_p2.json')
    browser.close()
