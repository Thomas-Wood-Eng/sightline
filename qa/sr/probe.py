import sys; sys.path.insert(0, '/c/Projects/paypal_hackathon/qa/sr')
from harness import *
with sync_playwright() as p:
    b, ctx = launch(p); page = ctx.new_page()
    run = Run('probe'); run.mark('load')
    page.goto(BASE + '/'); page.wait_for_timeout(1500)
    run.collect(page)
    print(page.evaluate("() => document.getElementById('setup').hidden"))
    run.show()
    b.close()
