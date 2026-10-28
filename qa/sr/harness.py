"""Screen-reader approximation harness for Sightline (Dev persona, keyboard only).

Not real NVDA. It records (a) what live regions would announce (MutationObserver on
aria-live / role=log|status|alert), (b) focus changes with an approximate accessible
name/role/description, and (c) keyboard-driven actions and the focus that results.
"""
import json, os, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get('SR_BASE', 'http://127.0.0.1:8792')  # SR_BASE=http://127.0.0.1:8811 for another server
OUT = 'C:/Projects/paypal_hackathon/qa/shots/sr'
os.makedirs(OUT, exist_ok=True)

INIT = r"""
(() => {
  window.__srlog = [];
  const T0 = performance.now();
  const rec = (kind, d) => window.__srlog.push(Object.assign({kind, t: Math.round(performance.now() - T0)}, d));
  const LIVE = '[aria-live],[role=log],[role=status],[role=alert]';
  const liveOf = (n) => { const el = n && (n.nodeType === 1 ? n : n.parentElement); return el ? el.closest(LIVE) : null; };
  const polite = (el) => {
    const a = el.getAttribute('aria-live'); if (a) return 'aria-live=' + a;
    const r = el.getAttribute('role');
    if (r === 'alert') return 'role=alert(assertive)';
    if (r === 'status') return 'role=status(polite)';
    if (r === 'log') return 'role=log(polite)';
    return '?';
  };
  const idOf = (el) => el ? (el.id ? '#' + el.id : el.tagName.toLowerCase()) : '';
  const txt = (id) => { const e = id && document.getElementById(id); return e ? e.textContent.trim() : ''; };
  const ids = (attr, el) => (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
  const nameOf = (el) => {
    const lb = ids('aria-labelledby', el); if (lb.length) return lb.map(txt).join(' ');
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) return l.textContent.trim(); }
    const wrap = el.closest('label'); if (wrap) return wrap.textContent.trim();
    if (el.tagName === 'BUTTON' || el.tagName === 'A') return el.textContent.trim();
    if (el.tagName === 'IMG') return el.alt || '';
    if (el.placeholder) return el.placeholder;
    return el.textContent ? el.textContent.trim().slice(0, 120) : '';
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role'); if (r) return r;
    const t = el.tagName;
    if (t === 'INPUT') return 'input[' + (el.type || 'text') + ']' ;
    return t.toLowerCase();
  };
  window.__describe = (el) => {
    if (!el) return 'null';
    const desc = ids('aria-describedby', el).map(txt).filter(Boolean).join(' ');
    let val = '';
    if (el.type === 'password') val = '(password, ' + el.value.length + ' chars)';
    else if (el.value !== undefined && el.tagName === 'INPUT') val = 'value="' + el.value + '"';
    const pressed = el.getAttribute('aria-pressed') ? ' pressed=' + el.getAttribute('aria-pressed') : '';
    return '[' + roleOf(el) + '] ' + JSON.stringify(nameOf(el)) + val + pressed + (desc ? ' desc=' + JSON.stringify(desc) : '') + ' ' + idOf(el);
  };
  window.__liveNow = (el) => { const l = liveOf(el); return l ? polite(l) : ''; };

  new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'childList') {
        const live = liveOf(m.target);
        if (!live) continue;
        const added = Array.from(m.addedNodes).map(n => (n.textContent || '').trim()).filter(Boolean);
        if (added.length) rec('live', {region: idOf(live), politeness: polite(live), text: added.join(' | ')});
      } else if (m.type === 'attributes') {
        const el = m.target;
        if (m.attributeName === 'aria-live') rec('attr', {el: idOf(el), what: 'aria-live=' + el.getAttribute('aria-live')});
        else if (m.attributeName === 'hidden' && (el.id === 'pin-form' || el.id === 'undo-box' || el.id === 'setup' || el.id === 'item'))
          rec('shown', {el: idOf(el), hidden: el.hidden});
      }
    }
  }).observe(document, {subtree: true, childList: true, attributes: true, attributeFilter: ['aria-live', 'hidden'], characterData: false});

  document.addEventListener('focusin', (e) => rec('focus', {desc: window.__describe(e.target)}), true);
})();
"""


def drain(page):
    return page.evaluate("() => { const x = window.__srlog || []; window.__srlog = []; return x; }")


def active(page):
    return page.evaluate("() => window.__describe(document.activeElement)")


class Run:
    def __init__(self, name):
        self.name = name
        self.events = []  # list of dicts: step, kind, ...
        self.steps = []
        self.step = ''

    def mark(self, step):
        self.step = step
        self.steps.append(step)

    def collect(self, page, note=''):
        for e in drain(page):
            e = dict(e); e['step'] = self.step
            self.events.append(e)

    def save(self):
        path = os.path.join(OUT, self.name + '_log.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.events, f, ensure_ascii=False, indent=1)
        return path

    def show(self, step_filter=None):
        for e in self.events:
            if step_filter and step_filter not in e['step']:
                continue
            if e['kind'] == 'live':
                print(f"  [{e['t']:>7}] SPOKEN {e['politeness']} {e['region']}: {e['text']}")
            elif e['kind'] == 'focus':
                print(f"  [{e['t']:>7}] FOCUS {e['desc']}")
            elif e['kind'] == 'shown':
                print(f"  [{e['t']:>7}] SHOWN {e['el']} hidden={e['hidden']}")
            elif e['kind'] == 'attr':
                print(f"  [{e['t']:>7}] ATTR {e['el']} {e['what']}")


def launch(p):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    ctx.add_init_script(INIT)
    return browser, ctx


def wait_reply(page, before, timeout=40000):
    """Wait until a new .turn appears in the log (one reply = one turn), then settle."""
    page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {before}", timeout=timeout)
    page.wait_for_timeout(400)


def turns(page):
    return page.evaluate("() => document.querySelectorAll('#log .turn').length")


def type_line(page, text, run, label):
    """Type into whatever has focus, then Enter. Returns the turn count before submit."""
    run.mark(label)
    n = turns(page)
    page.keyboard.type(text, delay=20)
    page.keyboard.press('Enter')
    return n


def tab_until(page, pred_js, max_tabs=80, shift=False):
    """Move focus with Tab/Shift+Tab until pred_js (JS over `el`) is true. Returns (count, desc)."""
    key = 'Shift+Tab' if shift else 'Tab'
    for i in range(1, max_tabs + 1):
        page.keyboard.press(key)
        ok = page.evaluate(f"() => {{ const el = document.activeElement; return !!({pred_js}); }}")
        if ok:
            return i, active(page)
    return -1, active(page)


def screenshot(page, name):
    page.screenshot(path=os.path.join(OUT, name + '.png'), full_page=False)
