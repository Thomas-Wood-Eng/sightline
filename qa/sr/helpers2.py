import sys, time; sys.path.insert(0, 'C:/Projects/paypal_hackathon/qa/sr')
from harness import *
STATE = 'C:/Projects/paypal_hackathon/qa/shots/sr/state.json'

def send_cmd(page, run, text, label=None, pace=16):
    """Type a command in the message box (focus must be there), Enter, wait for exactly one new reply."""
    run.mark(label or text)
    before = turns(page)
    page.keyboard.type(text, delay=15)
    page.keyboard.press('Enter')
    try:
        wait_reply(page, before)
    except Exception as e:
        print('TIMEOUT waiting for reply to', repr(text), e)
    time.sleep(pace)  # respects the 4 free-form questions per minute quota
    run.collect(page)
    last = page.evaluate("() => { const t = document.querySelectorAll('#log .turn'); const l = t[t.length-1]; return l ? l.innerText : ''; }")
    print(f'--- {text!r} turns_added={turns(page)-before} focus={active(page)}')
    print('    REPLY:', last.replace('\n', ' / '))
    return last

def show_step(run, step_sub):
    run.show(step_sub)
