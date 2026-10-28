"""Re-check of the screen-reader report issues after the fixes. Fresh session, keyboard only, live sandbox.
Run with the server on another port: SR_BASE=http://127.0.0.1:8811 python qa/sr/recheck.py"""
import sys; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from helpers2 import *

spoken = lambda run, step: [e['text'] for e in run.events if e['kind'] == 'live' and e['step'] == step]
srv = lambda page: page.evaluate("async () => (await (await fetch('/api/settings')).json()).state")
results = []


def check(name, ok, detail=''):
    results.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name, '|', str(detail)[:400])


def say(page, run, text, label=None, wait=True):
    run.mark(label or text)
    page.focus('#message'); before = turns(page)
    page.keyboard.type(text, delay=5); page.keyboard.press('Enter')
    if wait:
        wait_reply(page, before)
    page.wait_for_timeout(300); run.collect(page)
    return spoken(run, label or text)


with sync_playwright() as p:
    b, ctx = launch(p)
    page = ctx.new_page(); run = Run('recheck')
    page.goto(BASE + '/'); page.wait_for_selector('#log .turn')
    page.fill('#setup-pin', '1234'); page.fill('#setup-pin2', '1234'); page.click('text=Save and start')
    page.wait_for_selector('#setup', state='hidden'); run.collect(page)

    # 2: PIN-like text in the idle state
    s = say(page, run, '9999', 'pin idle')
    check('2 PIN-like idle: not echoed', all('9999' not in x for x in s) and '9999' not in page.inner_text('#log'), s)

    # 10: empty Enter
    s = say(page, run, '', 'empty enter')
    check('10 empty Enter: one short hint', s == ['Type a request first, or say help.'], s)

    # 4/5: brief default
    say(page, run, 'warm hoodie under 40', 'search')
    s = say(page, run, 'add it', 'add it')
    check('6 add it: concrete question', len(s) == 1 and 'Which one' in s[0] and '?' in s[0], s)
    s = say(page, run, 'tell me about the first one', 'describe')
    words = len(s[0].replace('You: tell me about the first one', '').split()) if s else 0
    check('4 describe at default (brief): short', words <= 45, f'{words} words: {s}')
    s = say(page, run, 'details', 'details')
    check('5 details gives more', s and len(s[0].split()) > words, s)

    # 3: double Enter on check out
    say(page, run, 'add it in medium', 'add')
    run.mark('double'); page.focus('#message'); before = turns(page)
    for _ in range(2):
        page.keyboard.type('check out', delay=5); page.keyboard.press('Enter')
    wait_reply(page, before, 60000); page.wait_for_timeout(2000); run.collect(page)
    check('3 double Enter: one Readback', turns(page) - before == 1, f'turns added {turns(page) - before}')
    s = say(page, run, 'check out', 'checkout again')
    check('3 repeated check out: short, no second Readback', s and 'No new hold was placed' in s[0] and 'Item 1' not in s[0], s)

    # 1: reload mid-checkout (awaiting_confirm, then awaiting_pin)
    run.mark('reload confirm'); page.reload(); page.wait_for_selector('#log .turn'); page.wait_for_timeout(500); run.collect(page)
    s = spoken(run, 'reload confirm')
    check('1 reload awaiting_confirm: says the hold', s and 'A payment of' in s[0] and 'US dollars is on hold' in s[0], s)
    say(page, run, 'confirm', 'confirm')
    run.mark('reload pin'); page.reload(); page.wait_for_selector('#log .turn'); page.wait_for_timeout(500); run.collect(page)
    s = spoken(run, 'reload pin')
    check('1 reload awaiting_pin: PIN box, focus, amount', s and 'waiting for your PIN' in s[0]
          and page.evaluate('document.activeElement.id') == 'pin' and page.is_visible('#pin-form'), [s, active(page)])

    # 8: Escape cancels, announced once
    run.mark('escape cancel'); before = turns(page); page.keyboard.press('Escape'); wait_reply(page, before, 60000)
    page.wait_for_timeout(1500); run.collect(page)
    s = spoken(run, 'escape cancel')
    check('8 Escape cancel: announced once', len(s) == 1 and 'Cancelled' in s[0], s)

    # 8 + 1: undo window reload, then Escape undo announced once
    say(page, run, 'check out', 'checkout 2'); say(page, run, 'confirm', 'confirm 2')
    run.mark('pin'); before = turns(page); page.keyboard.type('1234'); page.keyboard.press('Enter'); wait_reply(page, before, 60000)
    run.mark('reload undo'); page.reload(); page.wait_for_selector('#log .turn'); page.wait_for_timeout(500); run.collect(page)
    s = spoken(run, 'reload undo')
    check('1 reload undo_window: countdown restored', s and 'PIN was accepted' in s[0] and page.is_visible('#undo-btn'), s)
    run.mark('escape undo'); before = turns(page); page.keyboard.press('Escape'); wait_reply(page, before, 60000)
    page.wait_for_timeout(1500); run.collect(page)
    s = spoken(run, 'escape undo')
    check('8 Escape undo: announced once', len(s) == 1 and 'Undone' in s[0], s)

    # 11 + 7: settings with a wrong PIN, then a retype; short save message
    run.mark('settings wrong'); page.fill('#set-contact-name', 'Sam Test'); page.fill('#set-contact-email', 'sam@example.com')
    page.fill('#set-threshold', '50'); page.focus('#set-current-pin'); page.keyboard.type('9999'); page.click('text=Save settings')
    page.wait_for_function("document.getElementById('settings-status').textContent.startsWith('Error')"); run.collect(page)
    check('11 wrong PIN: field cleared, focus kept', page.input_value('#set-current-pin') == ''
          and page.evaluate('document.activeElement.id') == 'set-current-pin', active(page))
    run.mark('settings retype'); page.keyboard.type('1234'); page.click('text=Save settings')
    page.wait_for_function("document.getElementById('settings-status').textContent.startsWith('Settings saved')")
    page.wait_for_timeout(300); run.collect(page)
    st = page.inner_text('#settings-status')
    check('7 settings save: only the change, 15 words or fewer', len(st.split()) <= 15 and 'Sam Test' in st, st)

    # 2: PIN-like text while awaiting approval
    say(page, run, 'warm hoodie under 40', 'search 2'); say(page, run, 'add number 2 in medium', 'add big')
    say(page, run, 'check out', 'checkout approval')
    print('state:', srv(page))
    s = say(page, run, '1234', 'pin approval')
    check('2 PIN-like during approval: not echoed', all('1234' not in x for x in s) and '1234' not in page.inner_text('#log'), s)
    say(page, run, 'cancel', 'cleanup')

    run.save(); b.close()
print(f"\n{sum(ok for _, ok in results)}/{len(results)} checks passed")
