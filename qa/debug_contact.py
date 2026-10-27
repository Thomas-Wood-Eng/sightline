import sys, time, json
sys.path.insert(0, 'qa')
from maria_lib import *
from playwright.sync_api import sync_playwright
def show(page, tag):
    print(tag, page.evaluate("fetch('/api/settings').then(r=>r.json()).then(j=>JSON.stringify(j.contact))"))
with sync_playwright() as p:
    browser, ctx = new_context(p, 640, 360, dsf=2)
    ctx.add_cookies(json.load(open('qa/state_p3.json'))['cookies'])
    page = ctx.new_page(); page.goto(BASE + '/'); time.sleep(1)
    show(page, 'start')
    r = page.evaluate("""fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contact_name:'Alex',contact_email:'alex@example.com',approval_threshold:'50',current_pin:'1234',output_mode:null,per_order_cap:null,daily_cap:null,new_pin:null,verbosity:null,simple_mode:false,large_text:false,default_size:'',avoid_allergens:'',})}).then(r=>r.status+' '+r.text())""")
    print('post', r[:300])
    show(page, 'after post')
    print([ (c['name'], len(c['value'])) for c in ctx.cookies()])
    browser.close()
