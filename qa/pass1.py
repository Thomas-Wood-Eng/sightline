import sys, time
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright

P = 'p1'
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2, scheme='light')
    page = ctx.new_page()
    page.goto(BASE + '/')
    page.wait_for_selector('#log .turn')
    note(P, 'load', f'overflow={overflow(page)} setup_hidden={hidden_state(page,"#setup")}', shot(page, 'p1_01_load'))
    # Setup
    page.check('input[name=screen_reader][value=no]')
    page.click('#setup-pin'); page.keyboard.type('1234')
    page.click('#setup-pin2'); page.keyboard.type('1234')
    page.keyboard.press('Tab'); page.keyboard.press('Tab')  # to save button path not needed
    page.click('button:has-text("Save and start")')
    time.sleep(1.5)
    note(P, 'setup', 'saved', shot(page, 'p1_02_setup_saved'))
    note(P, 'setup_last_turn', last_turn(page)[:200])
    # Large text in Settings
    page.click('label:has-text("Large text")')
    page.click('button:has-text("Save settings")')
    time.sleep(1.5)
    note(P, 'large_text', 'on; overflow=' + str(overflow(page)), shot(page, 'p1_03_large_text'))
    page.evaluate("document.getElementById('message').scrollIntoView()")
    note(P, 'after_large', 'viewport top', shot(page, 'p1_04_chat_large'))
    browser.close()
