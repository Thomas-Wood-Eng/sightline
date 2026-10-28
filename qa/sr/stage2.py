import sys; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 900}, storage_state=STATE)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    run = Run('stage2')
    page.goto(BASE + '/'); page.wait_for_timeout(1000); run.collect(page)
    page.focus('#message')  # Dev arrived via the skip link; same effect
    run.mark('2a shop')
    for t in ['warm hoodie under 40', 'next', 'tell me about the first one', 'spell that', 'repeat',
              'what do people say about it', 'add it', 'medium', 'my cart']:
        send_cmd(page, run, t)
    run.collect(page)
    run.save(); ctx.storage_state(path=STATE); b.close()
