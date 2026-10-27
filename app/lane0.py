"""Lane 0: deterministic commands, no AI. parse() maps text to a command tuple or None; handle() runs it.

While a payment is on hold, handle() never returns None, so free text cannot reach an LLM mid-checkout.
"""
import json, re
from datetime import datetime
from pathlib import Path

from . import catalog, checkout, speech
from .speech import Reply

FEEDBACK = Path(__file__).resolve().parent.parent / 'feedback.jsonl'
WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
         'a': 1, 'an': 1, 'to': 2, 'too': 2, 'for': 4,  # common speech-recognition homophones
         **{w: i for i, w in enumerate(speech.ORDINALS, 1)}, 'last': -1, '1st': 1, '2nd': 2, '3rd': 3}
NUM = r'(\d+|' + '|'.join(sorted(WORDS, key=len, reverse=True)) + r')'
IT = r'(it|this|that|this one|that one|the item|the product|the current one)'

FIXED = [
    (r"(that is|that was|this is|you are|you're) (wrong|not right|incorrect)|wrong|not right", ('wrong',)),
    (r'help|what can i (do|say)|commands|options|what are (my|the) options|what do i say', ('help',)),
    (r'repeat( that| it)?|say (that|it) again|again|pardon|what|come again|sorry what', ('repeat',)),
    (r'spell( (that|it|the name|that again|the order number))?', ('spell',)),
    (r'next( one| item)?|skip', ('next',)),
    (r'back|previous( one| item)?|go back|prev', ('back',)),
    (r'(tell me )?more|more please', ('more', False)),
    (r'more results|show more|next page|keep going|any more|anything else|more options|other options', ('more', True)),
    (r'(show |read |view |open )?(my |the )?(cart|basket)|what is in (my|the) (cart|basket)|cart please', ('cart',)),
    (r'(clear|empty) (my |the )?(cart|basket)', ('clear',)),
    (r'check ?out|go to (the )?check ?out|proceed to (the )?check ?out|place (the |my )?order|pay( now)?|buy now'
     r'|i am ready to pay|complete (my |the )?(order|purchase)', ('checkout',)),
    (r'(i )?confirm( it| that| the (purchase|order|payment)| purchase| order| payment)?|yes,? confirm', ('confirm',)),
    (r'yes|yeah|yep|yup|sure|ok|okay|correct|go ahead', ('yes',)),
    (r'no|nope|nah|no thanks', ('no',)),
    (r'cancel( it| that| the order| order| the payment| payment| purchase| the purchase| checkout)?|never ?mind|abort',
     ('cancel',)),
    (r'stop|quiet|shh+|be quiet', ('stop',)),
    (r'(open |show )?settings|preferences', ('settings',)),
    (r'(link|connect|set up|add) (my )?pay ?pal( account)?', ('link',)),
]
FILLER_START = r'^(please|ok(ay)?|um+|uh+|so|hey sightline|sightline|can you|could you|i want to|i would like to|i\'d like to|let\'s|lets)\s+'
FILLER_END = r'\s+(please|now|for me|thanks|thank you)$'


def norm(text):
    t = text.lower().strip()
    t = t.replace('’', "'").replace("what's", 'what is').replace("that's", 'that is').replace("it's", 'it is')
    t = t.replace("i'll", 'i will').replace("i'm", 'i am')
    t = re.sub(r'[^\w\s\'$.]', ' ', t)
    t = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', t)  # drop full stops, keep decimals
    t = re.sub(r'\s+', ' ', t).strip()
    for _ in range(3):
        t = re.sub(FILLER_START, '', t)
        t = re.sub(FILLER_END, '', t)
    return t


def num(tok):
    return int(tok) if tok.isdigit() else WORDS.get(tok)


def target(t):
    """'it' | ('n', N) | ('name', words). Accepts: it, this one, 2, number 2, item two, the second (one)."""
    t = re.sub(r'^(the|item|option|product|number|no)\s+', '', t.strip())
    t = re.sub(r'^(number|item)\s+', '', t)
    if not t or re.fullmatch(IT, t):
        return 'it'
    m = re.fullmatch(NUM + r'( one| item)?', t)
    if m and num(m.group(1)) is not None:
        return ('n', num(m.group(1)))
    return ('name', t)


def parse(text):
    t = norm(text)
    if not t:
        return None
    if re.search(r'\b(cap|caps|limit|limits|budget|spending)\b', t):
        changing = r'\b(raise|increase|change|set|lower|remove|update|up|higher|bigger|double|lift|disable|turn off|make)\b'
        return ('caps',) if re.search(changing, t) else ('settings',)
    for pat, cmd in FIXED:
        if re.fullmatch(pat, t):
            return cmd
    m = re.fullmatch(NUM, t) or re.fullmatch(r'(?:number|item|option|no) ' + NUM, t) \
        or re.fullmatch(r'the ' + NUM + r'( one| item)?', t)
    if m and num(m.group(1)) is not None:
        return ('pick', num(m.group(1)))
    m = re.fullmatch(r'(add|put|i will take|i will have|i want|buy|get me|grab)\b\s*(.*)',
                     re.sub(r'\s*\b(to|in|into|on) (my |the )?(cart|basket)$', '', t))
    if m:
        rest, qty = m.group(2), 1
        q = re.match(NUM + r' (?:of )?(.*)', rest)
        if q and num(q.group(1)) and q.group(2) and not re.fullmatch(r'(one|item)', q.group(2)):
            qty, rest = num(q.group(1)), re.sub(r'^(them|those|these)$', 'it', q.group(2))
        tgt = target(rest)
        # only "add"/"put" may name a product; "buy a gift for mum" is a search, not an add
        if m.group(1) in ('add', 'put') or tgt == 'it' or tgt[0] == 'n':
            return ('add', max(1, min(qty, 10)), tgt)
        return None
    m = re.fullmatch(r'(?:remove|delete|take out|drop|take)\b\s*(.*?)(?: out)?',
                     re.sub(r'\s*\b(out of|from) (my |the )?(cart|basket)$', '', t))
    if m:
        return ('remove', target(m.group(1)))
    m = re.fullmatch(r'(?:describe|tell me (?:more )?about|details(?: (?:on|for|about|of))?|more (?:about|on)'
                     r'|what (?:does|do) (.*?) look like|what is (.*?) like|what is (.*?) made of)\s*(.*)', t)
    if m:
        return ('describe', target(next((g for g in m.groups() if g), '')))
    m = re.fullmatch(r'compare(?: (?:them|these|those|all|the results|both))?(.*)'
                     r'|which (?:one )?is (?:cheaper|cheapest|better|best)(.*)', t)
    if m:
        rest = next((g for g in m.groups() if g is not None), '')
        first = re.search(r'(?:first|top) (two|three|2|3)\b', rest)
        nums = list(range(1, num(first.group(1)) + 1)) if first else \
            [num(w) for w in re.findall(r'\b' + NUM + r'\b', rest) if num(w) and num(w) > 0]
        return ('compare', nums[:3])
    return None


# ---- execution -------------------------------------------------------------------------------------------------
def card(p):
    e = p.get('enriched') or {}
    return {'id': p['id'], 'name': p['name'], 'image': '/static/' + p['image'] if p.get('image') else None,
            'alt': e.get('short') or p['name']}


def show_results(s, products, what):
    """Shared with Lane 1: store up to 9 result ids, speak the first 3."""
    s['results'] = [p['id'] for p in products[:9]]
    s['page'], s['what'], s['focus'] = 0, what, None
    say, lines = speech.results(products[:3], 0, len(s['results']), what)
    if products:
        s['spell'] = products[0]['name']
    return Reply(say, lines)


def _results(s):
    return [catalog.get(i) for i in s.get('results', []) if catalog.get(i)]


def _focus(s, p):
    s['focus'], s['spell'] = p['id'], p['name']


def resolve(s, tgt, pool=None):
    """Find the product a target refers to. Numbers index the latest results (or `pool`, e.g. the cart)."""
    pool = pool if pool is not None else _results(s)
    if tgt == 'it':
        return catalog.get(s.get('focus') or '') or (pool[0] if len(pool) == 1 else None)
    if tgt[0] == 'n':
        n = len(pool) if tgt[1] == -1 else tgt[1]
        return pool[n - 1] if 1 <= n <= len(pool) else None
    words = set(catalog.tokens(tgt[1]))
    best = max(pool, key=lambda p: len(words & set(catalog.tokens(p['name']))), default=None)
    if best and words & set(catalog.tokens(best['name'])):
        return best
    hits = catalog.search(tgt[1], limit=1)
    return hits[0] if hits else None


def which(s):
    n = len(_results(s))
    return Reply('Which one? Say a number from the results, or search first.' if n else
                 'Search for something first, for example: warm hoodie under 40 dollars.')


HELP = ['Search by saying what you want, for example: warm hoodie under 40 dollars.',
        'Say a number to pick a result, then describe it, or add it.',
        'Next, back, more, repeat, and spell that work any time.',
        'Compare them; what is in my cart; remove it; check out.',
        'At checkout: confirm, then type your PIN. Or say cancel.',
        "If something I said is wrong, say: that is wrong."]


def _log_feedback(s, text):
    with FEEDBACK.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'t': datetime.now().isoformat(timespec='seconds'), 'said': text,
                            'last': s.get('last'), 'focus': s.get('focus')}) + '\n')


def handle(text, s):
    cmd = parse(text)
    st = checkout.state(s)
    if st in checkout.HOLDING:
        return _holding(cmd, text, s, st)
    if cmd is None:
        return None
    name, args = cmd[0], cmd[1:]
    led_spent = checkout.ledger(s)['spent']
    if name == 'repeat':
        last = s.get('last')
        return Reply(last['say'], last['lines']) if last else Reply('Nothing to repeat yet.')
    if name == 'help':
        return Reply('You can say:', HELP)
    if name == 'wrong':
        _log_feedback(s, text)
        return Reply('Thanks, I noted that. Say describe to hear exactly what the listing says, or ask again.')
    if name == 'spell':
        return Reply(speech.spell(s['spell'])) if s.get('spell') else Reply('Nothing to spell yet.')
    if name == 'stop':
        return Reply('Stopped.')
    if name in ('caps', 'settings'):
        lead = 'For your safety, spending caps cannot be changed by voice. ' if name == 'caps' else ''
        return Reply(lead + speech.settings_summary(checkout.caps(s), s.get('mode', 'screen_reader'),
                                                    bool(checkout.vault_id(s)), bool(s.get('pin')), led_spent))
    if name == 'link':
        return Reply("Opening PayPal's login page. PayPal's login is your security boundary; we never see your password.",
                     action='link')
    if name == 'pick':
        p = resolve(s, ('n', args[0]))
        if not p:
            return which(s)
        _focus(s, p)
        return Reply(speech.focus_line(s['results'].index(p['id']) + 1, p), focus=card(p))
    if name in ('next', 'back'):
        res = s.get('results', [])
        if not res:
            return which(s)
        i = res.index(s['focus']) if s.get('focus') in res else -1
        i = i + 1 if name == 'next' else (i - 1 if i >= 0 else 0)
        if not 0 <= i < len(res):
            return Reply('That was the last one. Say more, or search again.' if name == 'next' else 'That is the first one.')
        p = catalog.get(res[i])
        _focus(s, p)
        s['page'] = i // 3 * 3
        return Reply(speech.focus_line(i + 1, p), focus=card(p))
    if name == 'more':
        res, page = _results(s), s.get('page', 0)
        if page + 3 < len(res) and (args[0] or not s.get('focus')):
            s['page'], s['focus'] = page + 3, None
            say, lines = speech.results(res[page + 3:page + 6], page + 3, len(res), s.get('what', ''))
            return Reply(say, lines)
        if s.get('focus'):
            return _describe(s, catalog.get(s['focus']))
        return Reply('That is everything I found. Try a different search.' if res else which(s).say)
    if name == 'describe':
        p = resolve(s, args[0])
        return _describe(s, p) if p else which(s)
    if name == 'compare':
        res = _results(s)
        nums = args[0] or list(range(s.get('page', 0) + 1, min(s.get('page', 0) + 3, len(res)) + 1))
        items = [(n, res[n - 1]) for n in nums if 1 <= n <= len(res)]
        if len(items) < 2:
            return Reply('Search first, then say compare, or compare 1 and 3.')
        say, lines = speech.compare(items)
        return Reply(say, lines)
    if name == 'add':
        qty, tgt = args
        p = resolve(s, tgt)
        if not p:
            return which(s)
        cart = s.get('cart', [])
        for line in cart:
            if line[0] == p['id']:
                line[1] = min(line[1] + qty, 10)
                break
        else:
            cart.append([p['id'], qty])
        s['cart'] = cart
        _focus(s, p)
        return Reply(speech.added(p, qty, sum(q for _, q in cart)), focus=card(p))
    if name == 'remove':
        cart = s.get('cart', [])
        pool = [catalog.get(i) for i, _ in cart]
        p = resolve(s, args[0], pool) if args[0] != 'it' else catalog.get(s.get('focus') or '')
        if not p or p['id'] not in [i for i, _ in cart]:
            return Reply('That is not in your cart. Say cart to hear what is in it.')
        s['cart'] = [l for l in cart if l[0] != p['id']]
        return Reply(speech.removed(p, sum(q for _, q in s['cart'])))
    if name == 'clear':
        s['cart'] = []
        return Reply('Your cart is now empty.')
    if name == 'cart':
        say, lines = speech.cart([(catalog.get(i), q) for i, q in s.get('cart', []) if catalog.get(i)])
        return Reply(say, lines)
    if name == 'checkout':
        return checkout.start(s)
    if name in ('confirm', 'yes'):
        return checkout.confirm(s)
    if name in ('cancel', 'no'):
        return checkout.cancel(s) if name == 'cancel' else Reply('OK.')
    return None


def _describe(s, p):
    _focus(s, p)
    lines = speech.describe(p)
    return Reply(lines[0], lines[1:], focus=card(p))


def _holding(cmd, text, s, st):
    """A payment is on hold: only checkout words, repeat, spell, help and feedback are accepted."""
    name = cmd[0] if cmd else None
    if st == checkout.PIN and re.fullmatch(r'[\d\s-]{4,}', text.strip()):
        return Reply('For your safety, type the PIN in the PIN box, not the message box. Nothing was sent.')
    if name in ('confirm', 'yes'):
        return checkout.confirm(s)
    if name in ('cancel', 'no'):
        return checkout.cancel(s)
    if name in ('repeat', 'checkout'):
        last = s.get('last') if name == 'repeat' else None
        return Reply(last['say'], last['lines']) if last else checkout.start(s)
    if name == 'spell' and s.get('spell'):
        return Reply(speech.spell(s['spell']))
    if name == 'wrong':
        _log_feedback(s, text)
        return Reply('Thanks, I noted that. If the Readback is wrong, say cancel and nothing will be charged.')
    step = 'type your PIN in the PIN box' if st == checkout.PIN else 'say confirm'
    return Reply(f'A payment is on hold. To pay, {step}. To release it, say cancel. Say repeat to hear the Readback.')
