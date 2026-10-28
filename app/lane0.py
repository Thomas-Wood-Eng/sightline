"""Lane 0: deterministic commands, no AI. parse() maps text to a command tuple or None; handle() runs it.

While a payment is on hold, handle() never returns None, so free text cannot reach an LLM mid-checkout.
"""
import json, re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from . import catalog, checkout, db, paypal, speech
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
    (r'(more |the |full |all the )?details|give me (the |more )?details|tell me more about (it|this|that|this one|that one)',
     ('describe', 'it', 'more')),  # one level more detail than the setting
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
    (r"undo( it| that| the (payment|order|purchase))?|(do not|don't) pay|stop (the )?payment", ('undo',)),
    (r'stop|quiet|shh+|be quiet', ('stop',)),
    (r'(open |show )?settings|preferences', ('settings',)),
    (r'(link|connect|set up|add) (my )?pay ?pal( account)?', ('link',)),
    (r'(tell me (more )?about |what is |more about |explain |hear more about )?(pay ?pal )?(pay later|pay in (4|four|for))'
     r'( options?)?', ('paylater',)),
]
FILLER_START = r'^(please|ok(ay)?|um+|uh+|so|hey sightline|sightline|can you|could you|i want to|i would like to|i\'d like to|let\'s|lets)\s+'
FILLER_END = r'\s+(please|now|for me|thanks|thank you)$'


def norm(text):
    t = text.lower().strip()
    t = t.replace('’', "'").replace("what's", 'what is').replace("that's", 'that is').replace("it's", 'it is')
    t = t.replace("i'll", 'i will').replace("i'm", 'i am').replace("where's", 'where is')
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
    when = r'(today|this week|this month|last week|last month|in total|so far)'
    period = lambda p: {'this week': 'week', 'this month': 'month', 'last week': 'last_week', 'last month': 'last_month',
                        'in total': 'all', 'so far': 'all'}.get(p, p)
    m = re.fullmatch(r'how much (?:have i|did i|i have|i) (?:spent|spend)(?: ' + when + ')?'
                     r'|(?:my )?spending (today|this week|this month|last week|last month)', t)
    if m:
        return ('spent', period(next((g for g in m.groups() if g), 'today')))
    m = re.fullmatch(r'what (?:did|have) i (?:buy|bought|order|ordered|purchase|purchased|get|got) ' + when +
                     r'|(?:show |list |read )?(?:me )?(?:all )?my pay ?pal (?:purchases|orders|payments|transactions)', t)
    if m:  # the spending summary plus what was bought
        return ('spent', period(m.group(1) or 'all'), 'list')
    # dispute help: something went wrong with a delivered (or undelivered) order
    if re.search(r"\b(?:never (?:got|received|arrived|came|showed up)|(?:did not|didn't) (?:get|receive|arrive|come)"
                 r"|(?:has not|hasn't|have not|haven't) (?:arrived|come|got|received)|lost in the (?:post|mail))\b", t):
        return ('dispute', 'missing', t)
    if re.search(r"\b(?:broken|damaged|smashed|cracked|shattered|torn|faulty|defective|(?:does not|doesn't) work)\b", t) \
            and re.search(r'\b(?:arrived|came|got|received|is|was)\b', t):
        return ('dispute', 'broken', t)
    if re.search(r"(?:\bnot|n't) what i (?:ordered|bought)\b|\b(?:wrong (?:item|thing|product|order)"
                 r"|(?:sent|got|received|delivered) (?:me )?(?:the |a )?wrong)\b", t):
        return ('dispute', 'wrong', t)
    if re.search(r'\b(?:alert me|notify me|warn me|tell me (?:if|when)|let me know (?:if|when)|price alert|watch the price)\b', t) \
            and re.search(r'\b(?:cheaper|on sale|price|drops?|goes down|under|below|less than)\b', t):
        amount = re.search(r'\b(?:under|below|less than|to)\s*\$?(\d+(?:\.\d{1,2})?)', t)
        words = re.search(r'\b(?:if|when) (?:the )?(.+?) (?:gets|goes|is|drops|falls|comes)\b', t)
        return ('alert', amount.group(1) if amount else None, target(words.group(1)) if words else 'it')
    if re.search(r'\b(cap|caps|limit|limits|budget|spending)\b', t):
        changing = r'\b(raise|increase|change|set|lower|remove|update|up|higher|bigger|double|lift|disable|turn off|make)\b'
        return ('caps',) if re.search(changing, t) else ('settings',)
    if re.search(r'\b(i am|i wear) (a )?size\b|\bdefault size\b|\balways avoid\b|\b(no|never)\b.*\bever\b'
                 r'|\b(remember|save) (that )?(i|my)\b|\b(verbosity|simple mode|large text)\b', t):
        return ('prefs',)
    if re.fullmatch(r'(?:show |list |read )?(?:my |past |previous |recent |the )*orders|order history'
                    r'|what (?:have i|did i) (?:order|ordered|buy|bought)', t):
        return ('orders',)
    m = re.fullmatch(r'(?:check|photo check|look at|scan) (?:a photo of )?(?:my |the |this )?(.*?)\s*(?:package|parcel|delivery)'
                     r'|is (?:this|that|it) (?:really )?my (.*?)\s*(?:package|parcel|order|delivery)', t)
    if m:
        return ('package', m.group(1) or m.group(2) or '')
    m = re.fullmatch(r'(?:where is|track|status of|has|when will|when does) (?:my |the )?(.*?)\s*'
                     r'(?:order|package|parcel|delivery)(?: shipped| arrived| arrive| come)?'
                     r'|when (?:will|does) (?:it|my order) (?:arrive|come|get here)', t)
    if m:
        return ('track', m.group(1) or '')
    if re.fullmatch(r'(?:it is|this is|make it|make this|send it as|mark it as) a gift|gift mode( on)?|add a gift note', t):
        return ('gift',)
    if re.fullmatch(r'(?:it is |this is )?not a gift|(?:no|cancel|remove|turn off) (?:the )?gift(?: mode| note)?|gift mode off', t):
        return ('gift_off',)
    WL = r'(?:my |the )?(?:wish ?list|saved items|saved for later|saved list|favou?rites)'
    if re.fullmatch(r'(?:show |read |open |what is in )?' + WL + r'|what (?:did i|have i) saved', t):
        return ('wishlist',)
    m = re.fullmatch(r'(?:save|keep|add|put) ?(.*?) (?:for later|to ' + WL + r')|save (it|this|that|this one|that one)', t)
    if m:
        return ('save', target(m.group(1) or m.group(2) or ''))
    m = re.fullmatch(r'move ?(.*?) (?:to|into) (?:my |the )?(?:cart|basket)', t)
    if m:
        return ('move', target(m.group(1)))
    m = re.fullmatch(r'(?:order|buy|get) (.*?) again|reorder ?(.*)|(?:order|buy|get) my usual (.*)', t)
    if m:
        words = re.sub(r'\b(last|thing|things|order|one|item|stuff|usual|my|the|it|same)\b', ' ', next((g for g in m.groups() if g), ''))
        return ('reorder', ' '.join(words.split()))
    m = re.fullmatch(r'(?:return|refund|send back)\s+(.+?)(?: for a refund| please)?', t)
    if m:
        return ('return', m.group(1))
    for pat, cmd in FIXED:
        if re.fullmatch(pat, t):
            return cmd
    m = re.fullmatch(NUM, t) or re.fullmatch(r'(?:number|item|option|no) ' + NUM, t) \
        or re.fullmatch(r'the ' + NUM + r'( one| item)?', t)
    if m and num(m.group(1)) is not None:
        return ('pick', num(m.group(1)))
    m = re.fullmatch(r'the (\w+(?: \w+)?) one', t)  # "the black one"
    if m and m.group(1) not in WORDS:
        return ('pick', ('name', m.group(1)))
    m = re.fullmatch(r'(add|put|i will take|i will have|i want|buy|get me|grab)\b\s*(.*)',
                     re.sub(r'\s*\b(to|in|into|on) (my |the )?(cart|basket)$', '', t))
    if m:
        rest, qty = m.group(2), 1
        v = re.fullmatch(r'(.*?)\s*\b(?:in|size)\s+(?:size\s+|a\s+)?(.+)', rest)  # "add it in medium", "add 2 size L"
        rest, opt = (v.group(1), v.group(2)) if v else (rest, '')
        q = re.match(NUM + r' (?:of )?(.*)', rest)
        if q and num(q.group(1)) and q.group(2) and not re.fullmatch(r'(one|item)', q.group(2)):
            qty, rest = num(q.group(1)), re.sub(r'^(them|those|these)$', 'it', q.group(2))
        tgt = target(rest)
        # only "add"/"put" may name a product; "buy a gift for mum" is a search, not an add
        if m.group(1) in ('add', 'put') or tgt == 'it' or tgt[0] == 'n':
            return ('add', max(1, min(qty, 10)), tgt) + ((opt,) if opt else ())
        return None
    m = re.fullmatch(r'(?:remove|delete|take out|drop|take)\b\s*(.*?)(?: out)?',
                     re.sub(r'\s*\b(out of|from) (my |the )?(cart|basket)$', '', t))
    if m:
        return ('remove', target(m.group(1)))
    m = re.fullmatch(r'(?:describe|tell me (?:more )?about|details(?: (?:on|for|about|of))?|more (?:about|on)'
                     r'|what (?:does|do) (.*?) look like|what is (.*?) like|what is (.*?) made of)\s*(.*)', t)
    if m:
        return ('describe', target(next((g for g in m.groups() if g), '')))
    m = re.fullmatch(r'what (?:do|did) (?:people|reviewers|customers|buyers|others|users) (?:say|think)(?: (?:about|of) (.*))?'
                     r'|(?:read |any |show |the )*reviews?(?: (?:for|of|on|about) (.*))?|is (it|this|that) any good', t)
    if m:
        return ('reviews', target(next((g for g in m.groups() if g), '')))
    m = re.fullmatch(r'compare(?: (?:them|these|those|all|the results|both))?(.*)'
                     r'|which (?:one )?is (?:cheaper|cheapest|better|best)(.*)', t)
    if m:
        rest = next((g for g in m.groups() if g is not None), '')
        both = re.fullmatch(r'\s*(?:the |those |these )?(two|three|2|3)(?: of them| items| ones)?', rest)
        if both:  # "compare those two": the ones just heard, from the top of the page
            return ('compare', [], num(both.group(1)))
        first = re.search(r'(?:first|top) (two|three|2|3)\b', rest)
        nums = list(range(1, num(first.group(1)) + 1)) if first else \
            [num(w) for w in re.findall(r'\b' + NUM + r'\b', rest) if num(w) and num(w) > 0]
        return ('compare', nums[:3])
    return None


# ---- execution -------------------------------------------------------------------------------------------------
def card(p):
    e = p.get('enriched') or {}
    return {'id': p['id'], 'name': p['name'], 'image': '/static/' + p['image'] if p.get('image') else None,
            'alt': e.get('short') or p['name'], 'price': f"${p['price']:.2f}",
            'rating': f"{p['rating']} out of 5 stars, {speech.plural(p['review_count'], 'review')}"}


def show_results(s, products, what):
    """Shared with Lane 1: store up to 9 result ids, speak the first 3."""
    s['results'] = [p['id'] for p in products[:9]]
    s['page'], s['what'], s['focus'] = 0, what, None
    say, lines = speech.results(products[:per(s)], 0, len(s['results']), what, level(s))
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
    """Ask which result, naming the ones just heard: "Which one: 1, Fleece-lined pullover hoodie, or 2, ...?"""
    res, page = _results(s), s.get('page', 0)
    page = page if page < len(res) else 0
    if not res:
        return Reply('Search for something first, for example: warm hoodie under 40 dollars.')
    opts = [f'{n}, {speech.short_name(p, 3)}' for n, p in enumerate(res[page:page + per(s)], page + 1)]
    return Reply('Which one: ' + (', '.join(opts[:-1]) + ', or ' + opts[-1] if len(opts) > 1 else opts[0]) + '?')


HELP = ['Search by saying what you want, for example: warm hoodie under 40 dollars.',
        'Say a number to pick a result, then describe it, add it, or add it in medium.',
        'What do people say about it; compare them; save it for later; my saved items.',
        'Next, back, more, repeat, and spell that work any time.',
        "What is in my cart; remove it; it's a gift; check out.",
        'At checkout: confirm, then type your PIN. Say undo within 10 seconds to stop the payment.',
        'My orders; where is my order; how much did I spend this week; return the hoodie; order it again.',
        'Caps, PIN, trusted contact and preferences change only in Settings.',
        "If something I said is wrong, say: that is wrong."]


def _log_feedback(s, text):
    with FEEDBACK.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'t': datetime.now().isoformat(timespec='seconds'), 'said': text,
                            'last': checkout.ledger(s).get('last'), 'focus': s.get('focus')}) + '\n')


# ---- sizes and colours ----------------------------------------------------------------------------------------
SIZE_WORDS = [('double extra large', 'xxl'), ('extra extra large', 'xxl'), ('2xl', 'xxl'), ('extra large', 'xl'),
              ('x large', 'xl'), ('extra small', 'xs'), ('x small', 'xs'), ('medium', 'm'), ('large', 'l'), ('small', 's')]
SIZE_NUMS = {w: str(n) for w, n in WORDS.items() if w not in ('a', 'an', 'to', 'too', 'for') and isinstance(n, int) and n > 0}


def _size_tokens(text):
    t = ' ' + re.sub(r'(\d+)\s*(?:by|x)\s*(\d+)', r'\1x\2', re.sub(r'[^a-z0-9 ]', ' ', text.lower())) + ' '
    for a, b in SIZE_WORDS:
        t = t.replace(f' {a} ', f' {b} ')
    return [SIZE_NUMS.get(w, w) for w in t.split() if w not in ('us', 'size', 'in', 'a')]


def match_size(text, sizes):
    """'medium' -> 'M', 'us nine' -> 'US 9', '32 by 32' -> '32x32'; None if no listed size is named."""
    said = _size_tokens(text or '')
    for size in sizes:
        k = _size_tokens(size)
        if k and any(said[i:i + len(k)] == k for i in range(len(said))):
            return size
    return None


def bare_size(text):
    """'M', 'medium', 'size XL' on their own -> 'M', 'XL'; None for anything else."""
    said = _size_tokens(text)
    return said[0].upper() if len(said) == 1 and said[0] in ('xs', 's', 'm', 'l', 'xl', 'xxl') else None


def _size_only(s, text, size):
    """A size said on its own, with no size question open: the item in focus in that size, else ask which item."""
    p = resolve(s, 'it')
    if p and match_size(text, sizes_of(p)):
        return add(s, p, 1, text)
    if p and sizes_of(p):
        s['ask'] = {'add': [p['id'], 1, None]}  # the next answer can be the size
        return Reply(f"The {p['name']} does not come in size {size}. " + speech.ask_size(p, sizes_of(p)), focus=card(p))
    if _results(s):
        return Reply(f'Size {size} for which item? Say the number first, for example: add number 1 in {size}.')
    return Reply(f'Size {size} for which item? Search first, for example: hoodie. Then say add number 1 in {size}.')


def colours(p):
    return p.get('colours') or ([p['listing']['colour']] if p['listing'].get('colour') else [])


def match_colour(text, options):
    words = set(catalog.tokens(text or ''))
    best = max(options or [], key=lambda c: len(words & set(catalog.tokens(c))), default=None)
    return best if best and words & set(catalog.tokens(best)) else None


def _only_colour(text, p):
    words = set(catalog.tokens(text))
    return bool(words) and words <= {w for c in colours(p) for w in catalog.tokens(c)}


def sizes_of(p):
    return p['listing'].get('sizes') or []


def _plan(s, tgt):
    """"add the protection plan": a seller's add-on joins the cart only when the shopper names it."""
    if tgt == 'it' or tgt[0] != 'name':
        return None
    words = set(catalog.tokens(tgt[1])) - {'addon', 'add'}
    for pid in [s.get('focus')] + [l[0] for l in s.get('cart', [])]:
        a = catalog.get(f'{pid}-addon')
        if a and words and words <= set(catalog.tokens(a['plan'])):
            return a
    return None


def add(s, p, qty, opt=''):
    """Add with a size and colour. Never guesses a size: asks, unless a saved default size fits."""
    sizes = sizes_of(p)
    size = sizes[0] if len(sizes) == 1 else match_size(opt, sizes)
    note = ''
    if sizes and not size and match_size(prefs(s)['size'], sizes):
        size, note = match_size(prefs(s)['size'], sizes), ' Your default size from Settings.'
    chosen = s.get('opt') or {}
    colour = match_colour(opt, p.get('colours')) or (chosen.get('colour') if chosen.get('id') == p['id'] else None)
    if sizes and not size:
        s['ask'] = {'add': [p['id'], qty, colour]}
        _focus(s, p)
        return Reply(speech.ask_size(p, sizes), focus=card(p))
    if p.get('colours') and not colour:
        colour = p['colours'][0]
    variant = ', '.join(x for x in [f'size {size}' if len(sizes) > 1 else '', colour if p.get('colours') else ''] if x)
    cart = s.get('cart', [])
    for line in cart:
        if line[0] == p['id'] and (line[2] if len(line) > 2 else '') == variant:
            line[1] = min(line[1] + qty, 10)
            break
    else:
        cart.append([p['id'], qty, variant])
    s['cart'], s['opt'] = cart, None
    if p.get('addon_of'):
        return Reply(speech.added(p, qty, sum(l[1] for l in cart)))
    _focus(s, p)
    return Reply(speech.added(p, qty, sum(l[1] for l in cart), variant) + note, focus=card(p))


def _answer(ask, text, cmd, s):
    """The shopper was asked a question (gift note, or which size). Another command drops the question."""
    if 'refund' in ask:  # dispute help offered a refund: yes starts the usual return Readback
        if cmd and cmd[0] in ('yes', 'confirm'):
            o = db.get(ask['refund'][0])
            if o and o['lines'][ask['refund'][1]]['refunded'] == '0.00':
                return checkout.start_refund(s, o, ask['refund'][1])
            return Reply('That item was already refunded. Say my orders to hear them.')
        if cmd and cmd[0] in ('no', 'cancel', 'stop'):
            return Reply('OK, no refund started. You can still open a dispute in PayPal.')
        return None
    if 'gift' in ask:
        if cmd and cmd[0] in ('cancel', 'stop'):
            s.pop('gift', None)
            return Reply('Gift mode is off.')
        if re.fullmatch(r'no( note)?|none|skip|no thanks|nothing|without a note', norm(text)):
            return Reply('A gift with no note. Say check out when ready.')
        s['gift'] = text.strip()[:120]
        cut = ' I kept the first 120 characters.' if len(text.strip()) > 120 else ''
        return Reply(f"Gift note saved: {s['gift']}.{cut} It is sent to PayPal and read back before you pay.")
    pid, qty, colour = ask['add']
    p = catalog.get(pid)
    if p and match_size(text, sizes_of(p)):
        return add(s, p, qty, f'{text} {colour or ""}')
    if cmd and cmd[0] in ('cancel', 'no', 'stop'):
        return Reply('OK, not added.')
    if cmd is None and p and len(text.split()) <= 3:  # a short unclear answer; longer free text is a new request
        s['ask'] = ask
        return Reply(speech.ask_size(p, sizes_of(p)) + ' Or say cancel.')
    return None


def _sid(s):
    checkout.ledger(s)  # gives the session its id
    return s['sid']


def _find_order(s, words, need_open=False):
    """Newest order whose items match the words (any order if no words). need_open: only lines not yet refunded."""
    rows, want = db.orders(_sid(s)), set(catalog.tokens(words or ''))
    for o in rows:
        for l in o['lines']:
            if (not want or want & set(catalog.tokens(l['name']))) and (not need_open or l['refunded'] == '0.00'):
                return o
    return None


def prefs(s):
    return {'size': '', 'avoid': [], 'verbosity': 'brief', 'large_text': False, 'simple': False, **(s.get('prefs') or {})}


def level(s):
    """Verbosity from Settings; simple mode means the shortest replies."""
    return 'brief' if prefs(s)['simple'] else prefs(s)['verbosity']


def more_level(s):
    """"more", "details": one level up from the setting (brief is the default, details on request)."""
    return 'detailed' if level(s) in ('normal', 'detailed') else 'normal'


def per(s):
    """Results spoken per page: one at a time in simple mode."""
    return 1 if prefs(s)['simple'] else 3


def pin_like(text):
    """Only digits, spaces and dashes, with 4 or more digits (sizes like 32 and quantities stay usable)."""
    return bool(re.fullmatch(r'[\d\s-]+', text.strip())) and sum(c.isdigit() for c in text) >= 4


# ---- gift-card / pressure scam guard: fixed rules, no AI ----
GIFT_CARD = re.compile(r'\bgift ?cards?\b|\b(?:itunes|apple|google play|steam|amazon|target|walmart|ebay|vanilla) cards?\b')
SCAM = re.compile(
    r"\b(?:irs|internal revenue|tax (?:office|man|department|agency)|police|sheriff|warrant|arrest(?:ed)?|bail|jail"
    r"|social security|medicare|customs|(?:the |my )?bank (?:said|says|told|called|wants)|pay (?:a |the |my )?fine"
    r"|wire (?:money|transfer|it|the money)|western union|moneygram|bitcoin|crypto(?:currency)?"
    r"|keep (?:it|this) (?:a )?secret|(?:do not|don't) tell (?:anyone|anybody|my|your)"
    r"|(?:won|win) (?:a |the )?(?:prize|lottery|sweepstakes)|(?:prize|lottery|sweepstakes|processing) fee|tech support"
    r"|read (?:them|the numbers|the codes?|the card) (?:to|over|out)|scratch (?:off )?the back"
    r"|(?:on the phone|caller|called me)\b.*\b(?:told|said|says|wants|asked)"
    r"|(?:someone|somebody|a man|a woman|a guy|they|he|she) (?:told|asked) me to (?:buy|pay|send|get)"
    r"|urgent\b.*\b(?:told|said|says|called)|(?:told|said|says|called)\b.*\burgent"
    r"|(?:grandson|granddaughter|grandchild|grandkid|nephew|niece)\b.*\b(?:trouble|hospital|lawyer|help))\b")


def handle(text, s):
    """The scam guard runs first, on anything said outside a checkout; then the commands."""
    st = checkout.state(s)
    if st in checkout.HOLDING or st == checkout.UNDO or pin_like(text) or 'gift' in (s.get('ask') or {}):
        return _handle(text, s)  # a gift note like "keep it a secret" is not a scam cue
    t = norm(text)
    pressure, card_asked = SCAM.search(t), GIFT_CARD.search(t)
    if not (pressure or card_asked):
        return _handle(text, s)
    first = not checkout.scam_flag(s)
    checkout.flag_scam(s, text, bool(pressure))
    if pressure:
        return Reply(speech.scam_warning(bool(s.get('contact'))))
    r = _handle(text, s) or show_results(s, [p for p in catalog.PRODUCTS if p.get('gift_card')], 'gift cards')
    if first:
        r.say = f'{speech.gift_card_note()} {r.say}'
    return r


def _handle(text, s):
    cmd = parse(text)
    st = checkout.state(s)
    if st != checkout.PIN and pin_like(text):  # same reply whatever the digits: no hint whether they were the PIN
        return Reply("For your safety, numbers like a PIN are never shown or spoken. If you meant a quantity or size, "
                     "say it with words, like 'quantity 2'.")
    if st in checkout.HOLDING:
        return _holding(cmd, text, s, st)
    if st == checkout.UNDO:  # PIN accepted, capture pending: only undo stops it; anything else hears the countdown
        if cmd and cmd[0] in ('undo', 'cancel', 'no', 'stop'):
            return checkout.undo(s)
        return checkout.finalize(s)
    ask = s.pop('ask', None)
    if ask:
        r = _answer(ask, text, cmd, s)
        if r:
            return r
    if cmd is None:
        size = bare_size(text)
        return _size_only(s, text, size) if size else None
    name, args = cmd[0], cmd[1:]
    if name == 'repeat':
        last = checkout.ledger(s).get('last')
        return Reply(last['say'], last['lines']) if last else Reply('Nothing to repeat yet.')
    if name == 'help':
        return Reply('You can say:', HELP)
    if name == 'paylater':
        return Reply(speech.pay_later())
    if name == 'wrong':
        _log_feedback(s, text)
        return Reply('Thanks, I noted that. Say describe to hear exactly what the listing says, or ask again.')
    if name == 'spell':
        return Reply(speech.spell(s['spell'])) if s.get('spell') else Reply('Nothing to spell yet.')
    if name == 'stop':
        return Reply('Stopped.')
    if name == 'prefs':
        return Reply('Preferences can only be changed in the Settings form, never by chat, so nobody can change them '
                     'by talking to me. Right now: ' + speech.prefs_summary(prefs(s)))
    if name in ('caps', 'settings'):
        lead = 'For your safety, spending caps cannot be changed by voice. ' if name == 'caps' else ''
        return Reply(lead + speech.settings_summary(checkout.caps(s), s.get('mode', 'screen_reader'),
                                                    bool(checkout.vault_id(s)), bool(s.get('pin')), checkout.spent_today(s), prefs(s),
                                                    s.get('contact')))
    if name == 'link':
        return Reply("Opening PayPal's login page. PayPal's login is your security boundary; we never see your password.",
                     action='link')
    if name == 'pick' and isinstance(args[0], tuple):  # "the black one"
        focus, words = catalog.get(s.get('focus') or ''), args[0][1]
        if focus and _only_colour(words, focus):
            c = match_colour(words, focus['colours'])
            s['opt'] = {'id': focus['id'], 'colour': c}
            return Reply(f"{c.capitalize()} chosen for {focus['name']}. Say add it.", focus=card(focus))
        hits = [p for p in _results(s) if _only_colour(words, p)]
        if len(hits) != 1:
            return None  # not a colour we can pin down: let Lane 1 have it
        args = (s['results'].index(hits[0]['id']) + 1,)
    if name == 'pick':
        p = resolve(s, ('n', args[0]))
        if not p:
            return which(s)
        _focus(s, p)
        return Reply(speech.focus_line(s['results'].index(p['id']) + 1, p, level(s)), focus=card(p))
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
        s['page'] = i // per(s) * per(s)
        return Reply(speech.focus_line(i + 1, p, level(s)), focus=card(p))
    if name == 'more':
        res, page, n = _results(s), s.get('page', 0), per(s)
        if page + n < len(res) and (args[0] or not s.get('focus')):
            s['page'], s['focus'] = page + n, None
            say, lines = speech.results(res[page + n:page + 2 * n], page + n, len(res), s.get('what', ''), level(s))
            return Reply(say, lines)
        if s.get('focus'):  # "tell me more" about the item: one level more detail than the setting
            return _describe(s, catalog.get(s['focus']), more_level(s))
        return Reply('That is everything I found. Try a different search.' if res else which(s).say)
    if name == 'describe':
        p = resolve(s, args[0])
        return _describe(s, p, more_level(s) if len(args) > 1 else None) if p else which(s)
    if name == 'orders':
        rows = db.orders(_sid(s))
        if rows:
            s['spell'] = rows[0]['order_id']
        say, lines = speech.orders(rows)
        return Reply(say, lines)
    if name == 'track':
        o = _find_order(s, args[0])
        if not o:
            return Reply('I could not find that order. Say my orders to hear them.')
        try:
            status = paypal.get_order(o['order_id']).get('status', 'unknown')
        except paypal.PayPalError:
            status = 'not reachable just now'
        s['spell'] = o['order_id']
        return Reply(speech.track(o, status))
    if name == 'package':
        o = _find_order(s, args[0]) or _find_order(s, '')
        if not o:
            return Reply('You have no orders to check yet. Say my orders to hear them.')
        s['package'] = o['order_id']
        return Reply(f'Take or choose a photo of what arrived with the Package photo button, under the message box. '
                     f'I will compare it with your order of {speech._what(o)}. The photo goes to Google Gemini to '
                     'check it, and Sightline does not keep it.', action='photo')
    if name == 'spent':
        today = date.today()
        monday, first = today - timedelta(days=today.weekday()), today.replace(day=1)
        since, until = {'today': (today, None), 'week': (monday, None), 'month': (first, None),
                        'last_week': (monday - timedelta(days=7), monday),
                        'last_month': ((first - timedelta(days=1)).replace(day=1), first), 'all': (date.min, None)}[args[0]]
        until = until and until.isoformat()
        say = speech.spending(args[0], *db.spent(_sid(s), since.isoformat(), until))
        if len(args) == 1:
            return Reply(say)
        rows = db.between(_sid(s), since.isoformat(), until)
        if rows:
            s['spell'] = rows[0]['order_id']
        return Reply(say, speech.purchases(rows))
    if name == 'gift':
        s['gift'], s['ask'] = s.get('gift') or '', {'gift': 1}
        return Reply('Gift mode on. What should the gift note say? Type or say it now, or say no note.')
    if name == 'gift_off':
        s.pop('gift', None)
        return Reply('Gift mode is off. No gift note will be sent.')
    if name == 'save':
        cart, wish = s.get('cart', []), s.get('wish', [])
        pool = _results(s) + [catalog.get(l[0]) for l in cart]
        p = resolve(s, args[0], pool if args[0] != 'it' else None)
        if not p or p.get('addon_of'):
            return which(s)
        moved = [l for l in cart if l[0] == p['id']]
        s['cart'] = [l for l in cart if l[0] != p['id']]
        variant = moved[0][2] if moved and len(moved[0]) > 2 else ''
        if [p['id'], variant] not in wish:
            wish.append([p['id'], variant])
        s['wish'] = wish[-20:]
        _focus(s, p)
        return Reply(f"Saved for later: {speech.item_name(p, variant)}." + (' Moved out of your cart.' if moved else '')
                     + ' Say my saved items to hear them.', focus=card(p))
    if name == 'wishlist':
        say, lines = speech.wishlist([(catalog.get(i), v) for i, v in s.get('wish', []) if catalog.get(i)], db.alerts(_sid(s)))
        return Reply(say, lines)
    if name == 'alert':
        amount, tgt = args
        wish = [catalog.get(i) for i, _ in s.get('wish', []) if catalog.get(i)]
        p = resolve(s, tgt, wish + _results(s)) if tgt != 'it' else \
            catalog.get(s.get('focus') or '') or (wish[0] if len(wish) == 1 else None)
        if not p or p.get('addon_of'):
            return Reply('Which item? Pick one first, or say: alert me when the hoodie is under 30 dollars.')
        price = Decimal(str(p['price']))
        goal = Decimal(amount) if amount else price - Decimal('0.01')
        if goal <= 0:
            return Reply('Say an amount above zero, for example: alert me under 30 dollars.')
        if goal >= price:
            return Reply(speech.alert_already(p, goal), focus=card(p))
        if p['id'] not in [i for i, _ in s.get('wish', [])]:
            s['wish'] = (s.get('wish', []) + [[p['id'], '']])[-20:]
        db.set_alert(_sid(s), p['id'], f'{goal:.2f}')
        _focus(s, p)
        return Reply(speech.alert_set(p, goal, bool(amount)), focus=card(p))
    if name == 'move':
        wish = [(catalog.get(i), v) for i, v in s.get('wish', []) if catalog.get(i)]
        pool = [p for p, _ in wish]
        focus = catalog.get(s.get('focus') or '')
        if args[0] == 'it':
            p = focus if focus in pool else (pool[0] if len(pool) == 1 else None)
        else:
            p = resolve(s, args[0], pool)
        if p not in pool:
            return Reply('That is not in your saved items. Say my saved items to hear them.')
        variant = next(v for q, v in wish if q is p)
        s['wish'] = [l for l in s['wish'] if l != [p['id'], variant]]
        return add(s, p, 1, variant)
    if name == 'reorder':
        rows = db.orders(_sid(s))
        want = set(catalog.tokens(args[0]))
        past = [l for o in rows for l in o['lines'] if want & set(catalog.tokens(l['name']))]
        if want and past:  # "my usual coffee": the matching line ordered most often
            names = [l['name'] for l in past]
            lines = [next(l for l in past if l['name'] == max(set(names), key=names.count))]
        else:
            lines = rows[0]['lines'] if rows and not want else []
        lines = [l for l in lines if catalog.get(l['pid'])]
        if not lines:
            return Reply('I could not find that in your past orders. Say my orders to hear them.')
        cart = s.get('cart', [])
        for l in lines:
            p = catalog.get(l['pid'])
            variant = l['name'][len(p['name']) + 2:-1] if l['name'].startswith(p['name'] + ' (') else ''
            cart.append([l['pid'], l['qty'], variant])
        s['cart'] = cart
        r = checkout.start(s)
        r.say = f"Added again: {', '.join(l['name'] for l in lines)}. {r.say}"
        return r
    if name == 'dispute':
        kind, words = args
        focus = (catalog.get(s.get('focus') or '') or {}).get('name', '')
        o = next((x for x in (_find_order(s, w, need_open=True) for w in (words, focus, '')) if x), None)
        if not o:
            return Reply(speech.protection(kind) + ' I could not find an order of yours that is not already refunded. '
                         'Say my orders to hear them.')
        want = set(catalog.tokens(words)) | set(catalog.tokens(focus))
        open_ = [i for i, l in enumerate(o['lines']) if l['refunded'] == '0.00']
        i = next((i for i in open_ if want & set(catalog.tokens(o['lines'][i]['name']))), open_[0])
        s['ask'] = {'refund': [o['order_id'], i]}
        s['spell'] = o['order_id']
        return Reply(speech.protection(kind), [speech.offer_refund(o, o['lines'][i])])
    if name == 'return':
        words = args[0]
        if target(words) == 'it':
            words = (catalog.get(s.get('focus') or '') or {}).get('name', '')
        o = _find_order(s, words, need_open=True)
        if not o:
            return Reply('I could not find that in an order that is not already refunded. Say my orders to hear them.')
        want = set(catalog.tokens(words))
        i = next(i for i, l in enumerate(o['lines'])
                 if l['refunded'] == '0.00' and (not want or want & set(catalog.tokens(l['name']))))
        return checkout.start_refund(s, o, i)
    if name == 'reviews':
        p = resolve(s, args[0])
        if not p:
            return which(s)
        _focus(s, p)
        say, lines = speech.reviews(p, catalog.REVIEWS.get(p['id']))
        return Reply(say, lines, focus=card(p))
    if name == 'compare':
        res, page, count = _results(s), s.get('page', 0), (args[1] if len(args) > 1 else 3)
        nums = args[0] or list(range(page + 1, min(page + count, len(res)) + 1))
        if len(nums) == 1 and s.get('focus') in s.get('results', []):  # "compare it with number 3"
            nums = [s['results'].index(s['focus']) + 1, *nums]
        items = [(n, res[n - 1]) for n in dict.fromkeys(nums) if 1 <= n <= len(res)]
        if len(items) < 2:
            return Reply('Search first, then say compare, or compare 1 and 3.')
        say, lines = speech.compare(items, level(s))
        return Reply(say, lines)
    if name == 'add':
        qty, tgt, *opt = args
        opt = opt[0] if opt else ''
        focus = catalog.get(s.get('focus') or '')
        if tgt != 'it' and tgt[0] == 'name' and focus and _only_colour(tgt[1], focus):
            p, opt = focus, f'{tgt[1]} {opt}'  # "add the black one": a colour of the item in focus
        elif _plan(s, tgt):
            p = _plan(s, tgt)
        else:
            p = resolve(s, tgt)
        if not p:
            return which(s)
        return add(s, p, qty, opt)
    if name == 'remove':
        cart = s.get('cart', [])
        pool = [catalog.get(l[0]) for l in cart]
        p = resolve(s, args[0], pool) if args[0] != 'it' else catalog.get(s.get('focus') or '')
        if not p or p['id'] not in [l[0] for l in cart]:
            return Reply('That is not in your cart. Say cart to hear what is in it.')
        s['cart'] = [l for l in cart if l[0] != p['id']]
        return Reply(speech.removed(p, sum(l[1] for l in s['cart'])))
    if name == 'clear':
        s['cart'] = []
        return Reply('Your cart is now empty.')
    if name == 'cart':
        say, lines = speech.cart(checkout.cart_lines(s.get('cart', [])))
        return Reply(say, lines)
    if name == 'checkout':
        return checkout.start(s)
    if name in ('confirm', 'yes'):
        return checkout.confirm(s)
    if name in ('cancel', 'no'):
        return checkout.cancel(s) if name == 'cancel' else Reply('OK.')
    if name == 'undo':
        return checkout.undo(s)
    return None


def price_drops(s):
    """Price-drop alerts that are now due, each said once, on the next turn. Never in the middle of a payment."""
    st = checkout.state(s)
    if st in checkout.HOLDING or st == checkout.UNDO or 'sid' not in s:
        return ''
    out = []
    for pid, a in db.alerts(s['sid']).items():
        p = catalog.get(pid)
        if p and not a['told'] and Decimal(str(p['price'])) <= Decimal(a['target']):
            db.alert_told(s['sid'], pid)
            out.append(speech.price_drop(p, a['target']))
    return ' '.join(out)


def _describe(s, p, lvl=None):
    _focus(s, p)
    lines = speech.describe(p, lvl or level(s))
    return Reply(lines[0], lines[1:], focus=card(p))


def _holding(cmd, text, s, st):
    """A payment is on hold: only checkout words, repeat, spell, help and feedback are accepted."""
    name = cmd[0] if cmd else None
    if st == checkout.APPROVAL and name not in ('cancel', 'no', 'undo', 'repeat', 'spell'):
        news = checkout.approval_news(s)
        if news and name in ('confirm', 'yes') and checkout.state(s) == checkout.CONFIRM:
            # approved and the shopper already said confirm: go straight to the PIN instead of asking twice
            nxt = checkout.confirm(s)
            return Reply(f'{news.say.split(". Say confirm")[0]}. {nxt.say}', nxt.lines)
        if news:
            return news
    if st == checkout.PIN and pin_like(text):
        return Reply('For your safety, type the PIN in the PIN box, not the message box. Nothing was sent.')
    if name in ('confirm', 'yes'):
        return checkout.confirm(s)
    if name in ('cancel', 'no', 'undo'):
        return checkout.cancel(s)
    if name == 'repeat' and s['co'].get('say'):  # "say repeat to hear the Readback" means the Readback, not the last reply
        return Reply(s['co']['say'], s['co']['lines'])
    if name in ('repeat', 'checkout'):
        last = checkout.ledger(s).get('last') if name == 'repeat' else None
        return Reply(last['say'], last['lines']) if last else checkout.start(s)
    if name == 'spell' and s.get('spell'):
        return Reply(speech.spell(s['spell']))
    if name == 'paylater':  # explains only: the hold stays as it is, paid in full on confirm
        return Reply(speech.pay_later() + ' To pay this order in full, say confirm. To release the hold, say cancel.')
    if name == 'wrong':
        _log_feedback(s, text)
        return Reply('Thanks, I noted that. If the Readback is wrong, say cancel and nothing will be charged.')
    if s['co'].get('kind') == 'refund':
        step = 'type your PIN in the PIN box' if st == checkout.PIN else 'say confirm'
        return Reply(f'A return is waiting. To get the refund, {step}. To keep the item, say cancel.')
    if st == checkout.APPROVAL:
        return Reply('This order is waiting for approval from your trusted contact. Say cancel to release the hold, '
                     'or say repeat to hear the Readback.')
    step = 'type your PIN in the PIN box' if st == checkout.PIN else 'say confirm'
    return Reply(f'A payment is on hold. To pay, {step}. To release it, say cancel. Say repeat to hear the Readback.')
