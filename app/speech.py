"""Every user-facing sentence that contains a number is rendered here, from data, by template.

Inputs are catalogue records or PayPal responses; free text from an LLM only ever passes through guard(),
which drops any sentence that mentions money or a number-like price.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class Reply:
    say: str
    lines: list = field(default_factory=list)
    focus: dict | None = None   # product card shown beside the transcript: id, name, image, alt
    action: str | None = None   # 'link' tells the page to open the PayPal login

ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth']
MONEY_RE = re.compile(r'[$€£]|\d+(\.\d\d)?\s*(dollars?|cents?|bucks|usd)\b|\bprice is\b|\bcosts?\s+\d', re.I)


def money(x):
    """Browse lines: "$34.99"."""
    return f'${Decimal(str(x)):.2f}'


def usd(x):
    """Checkout and caps: currency named in words."""
    return f'{Decimal(str(x)):.2f} US dollars'


def guard(text):
    """Drop any sentence of free (LLM) text that states money. Returns the safe remainder."""
    if not text:
        return ''
    keep = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if not MONEY_RE.search(s)]
    return ' '.join(keep)


def plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


def short_name(p, max_words=10):
    w = p['name'].split()
    return ' '.join(w[:max_words])


def result_line(n, p, level='normal'):
    """"1. Fleece-lined pullover hoodie, $34.99, 4.6 stars" (15 words or fewer at every verbosity level)."""
    if level == 'brief':
        return f"{n}. {short_name(p)}, {money(p['price'])}"
    if level == 'detailed':
        return f"{n}. {short_name(p, 7)}, {money(p['price'])}, {p['rating']} stars, {plural(p['review_count'], 'review')}"
    return f"{n}. {short_name(p)}, {money(p['price'])}, {p['rating']} stars"


def results(products, start, total, what, level='normal'):
    if not products:
        return f'No matches for {what}. Try other words, or say help.', []
    end = start + len(products)
    say = f'{plural(total, "result")} for {what}.' if start == 0 else f'Results {start + 1} to {end} of {total}.'
    if end < total:
        say += ' Say more for the next ones.'
    return say, [result_line(start + i + 1, p, level) for i, p in enumerate(products)]


def focus_line(n, p, level='normal'):
    if level == 'brief':
        return f"Number {n}: {p['name']}, {money(p['price'])}. Say describe, or add it."
    return (f"Number {n}: {p['name']}, {money(p['price'])}, {p['rating']} stars from "
            f"{plural(p['review_count'], 'review')}. Say describe, or add it.")


def delivery_date(days, today=None):
    d = (today or date.today()) + timedelta(days=int(days))
    return f'{d:%A}, {d:%B} {d.day}'


def _ns(v):
    if v in (None, '', []):
        return 'not stated'
    if isinstance(v, list):
        return v[0] if len(v) == 1 else ', '.join(v[:-1]) + ' or ' + v[-1]
    return str(v)


def describe(p, level='normal'):
    """What it is, size, colour, material, condition, in the box, allergens. Listing vs photo kept apart.
    brief: what it is and the price line; detailed: adds prepared questions and answers."""
    l, e = p.get('listing') or {}, p.get('enriched') or {}
    lines = [f"{p['name']}. " + (guard(e.get('description')) or guard(l.get('description')) or '')]
    size = l.get('sizes') or l.get('dimensions')
    lines.append(f"Listing says: size {_ns(size)}. Colour {_ns(l.get('colour'))}. Material {_ns(l.get('material'))}. "
                 f"Condition {_ns(l.get('condition'))}. In the box: {_ns(l.get('in_box'))}."
                 # allergens matter for food; for a hoodie "allergens not stated" is just noise
                 + (f" Allergens {_ns(l.get('allergens'))}." if p['category'] == 'grocery' or l.get('allergens') else '')
                 + (f" Care: {l['care']}." if l.get('care') else ''))
    photo = [f"{f['label']}: {guard(f['value'])}" for f in e.get('facts', []) if f.get('source') == 'photo' and guard(f['value'])]
    if photo:
        lines.append('Photo suggests, unverified: ' + '; '.join(photo) + '.')
    lines.append(f"{money(p['price'])}, {p['rating']} stars from {plural(p['review_count'], 'review')}. "
                 f"{'Free shipping' if not p['shipping'] else 'Shipping ' + money(p['shipping'])}. Arrives about {delivery_date(p['delivery_days'])}. "
                 f"Sold by {p['seller']}.")
    risky = warnings([(p, 1, '')])  # dark-pattern warnings are never trimmed by verbosity
    if level == 'brief':  # food keeps its allergens even in brief mode: never left unsaid
        food = [f"Listing says: allergens {_ns(l.get('allergens'))}."] if p['category'] == 'grocery' else []
        return [lines[0], *food, lines[-1], *risky]
    lines += risky
    if level == 'detailed':
        qa = [guard(f"{q['q']} {q['a']}") for q in e.get('qa', [])[:3]]
        lines += [f'Common question: {x}' for x in qa if x]
    return lines


def reviews(p, data):
    """'What do people say?': the precomputed summary of the demo reviews. Counts and the average come from the
    review data; summary phrases are model-written, so any with a digit or money is dropped."""
    if not data or not data.get('reviews'):
        return f"There are no reviews for {p['name']} yet.", []
    stars = [r['stars'] for r in data['reviews']]
    avg = (Decimal(sum(stars)) / len(stars)).quantize(Decimal('0.1'))
    clean = lambda xs: [x.strip().rstrip('.') for x in xs or [] if isinstance(x, str) and guard(x) and not re.search(r'\d', x)]
    sm = data.get('summary') or {}
    lines = []
    if clean(sm.get('pros')):
        lines.append(f"People like: {'; '.join(clean(sm['pros']))}.")
    if clean(sm.get('cons')):
        lines.append(f"Downsides: {'; '.join(clean(sm['cons']))}.")
    if clean([sm.get('complaint')]):
        lines.append(f"Most repeated complaint: {clean([sm['complaint']])[0]}.")
    return f"Reviews say, from {plural(len(stars), 'demo review')} averaging {avg} stars:", lines


def _best(items, key, reverse=False):
    """items: [(n, product)]; returns the winners' numbers and the winning value."""
    vals = [key(p) for _, p in items]
    best = max(vals) if reverse else min(vals)
    return [n for (n, p), v in zip(items, vals) if v == best], best


def compare(items):
    """items: [(number, product)], at most 3. One attribute per line, computed here, never by an LLM."""
    items = items[:3]
    name = lambda ns: ' and '.join(f"number {n}, {short_name(dict(items)[n], 4)}" for n in ns)
    tie = lambda ns: 'Tie: ' if len(ns) > 1 else ''
    out = []
    ns, v = _best(items, lambda p: Decimal(str(p['price'])))
    out.append(f'Cheapest: {tie(ns)}{name(ns)}, {money(v)}.')
    ns, v = _best(items, lambda p: p['rating'], reverse=True)
    out.append(f'Best rated: {tie(ns)}{name(ns)}, {v} stars.')
    ns, v = _best(items, lambda p: p['review_count'], reverse=True)
    out.append(f"Most reviews: {tie(ns)}{name(ns)}, {plural(v, 'review')}.")
    ns, v = _best(items, lambda p: Decimal(str(p['price'])) + Decimal(str(p['shipping'])))
    out.append(f'Lowest price with shipping: {tie(ns)}{name(ns)}, {money(v)}.')
    ns, v = _best(items, lambda p: p['delivery_days'])
    out.append(f"Fastest delivery: {tie(ns)}{name(ns)}, {plural(v, 'day')}.")
    return f'Comparing {plural(len(items), "item")}, one point at a time.', out


def item_name(p, variant=''):
    """Name plus chosen size/colour; this exact string goes to PayPal, so the Readback repeats it."""
    return f"{p['name']} ({variant})" if variant else p['name']


def cart(lines_in):
    """lines_in: [(product, qty, variant)]."""
    if not lines_in:
        return 'Your cart is empty.', []
    total = sum(Decimal(str(p['price'])) * q for p, q, _ in lines_in)
    n = sum(q for _, q, _ in lines_in)
    lines = [f"{i}. {item_name(p, v)}, quantity {q}, {money(p['price'])} each." for i, (p, q, v) in enumerate(lines_in, 1)]
    lines.append(f'Items total {money(total)}, before shipping and tax. Say check out when ready.')
    return f"Your cart has {plural(n, 'item')}.", lines


def added(p, qty, cart_count, variant=''):
    return f"Added: {item_name(p, variant)}, quantity {qty}. Cart has {plural(cart_count, 'item')}."


def ask_size(p, sizes):
    return f"Which size? {p['name']} comes in {_ns(sizes)}. Say the size, for example: {sizes[len(sizes) // 2]}."


def removed(p, cart_count):
    return f"Removed: {p['name']}. Cart has {plural(cart_count, 'item')}."


def cap_refusal(kind, cap, total, spent=None):
    """kind: 'order' or 'daily'."""
    total, cap = Decimal(str(total)), Decimal(str(cap))
    if kind == 'order':
        over = total - cap
        return (f'Not placed. This order totals {usd(total)}. Your per-order cap is {usd(cap)}, '
                f'so it is {usd(over)} over. Remove something, or change the cap in Settings.')
    spent = Decimal(str(spent or 0))
    over = spent + total - cap
    return (f'Not placed. This order totals {usd(total)}, and you have spent {usd(spent)} today. '
            f'Your daily cap is {usd(cap)}, so it is {usd(over)} over. Change the cap in Settings if you need to.')


def warnings(lines_in):
    """Scam and dark-pattern guard, from catalogue data by fixed rules (never an LLM). lines_in: [(product, qty, variant)]."""
    ids, out = {p['id'] for p, _, _ in lines_in}, []
    for p, _, _ in lines_in:
        if p.get('subscription'):
            out.append(f"Heads up: {p['name']} is a subscription that renews every {p['subscription']} until you cancel.")
        if p.get('urgency'):
            out.append(f"Heads up: the listing for {p['name']} says: {p['urgency']} That is sales pressure. "
                       'We cannot check it, so take your time.')
        ship, price = Decimal(str(p['shipping'])), Decimal(str(p['price']))
        if ship >= 10 and ship >= price * Decimal('0.4'):
            out.append(f"Heads up: shipping for {p['name']} is {usd(ship)}, unusually high for an item costing {usd(price)}.")
        a = p.get('addon')
        if a and a.get('preticked') and p['id'] + '-addon' not in ids:
            out.append(f"Heads up: the seller pre-ticks a {a['name']} for {usd(a['price'])}. I did not add it. "
                       f"Say add the {a['name']} only if you want it.")
    return out


def readback(order, meta):
    """The Readback. Every amount comes from PayPal's order response; meta gives delivery days and seller
    (catalogue data, not money). Fixed order: item, quantity, unit price, shipping, tax, total, delivery, seller."""
    pu = order['purchase_units'][0]
    amt, bd = pu['amount'], pu['amount']['breakdown']
    cur = amt['currency_code']
    assert cur == 'USD', cur
    lines = [f"Item {i}: {it['name']}. Quantity {it['quantity']}. Unit price {usd(it['unit_amount']['value'])}."
             for i, it in enumerate(pu.get('items', []), 1)]
    lines += [f"Shipping: {usd(bd['shipping']['value'])}.",
              f"Tax: {usd(bd['tax_total']['value'])}.",
              f"Total: {usd(amt['value'])}.",
              f"Delivery by {delivery_date(meta['delivery_days'])}.",
              f"Seller: {meta['seller']}.",
              *meta.get('warnings', []),
              'Say confirm to continue to your PIN, or cancel to release the hold.']
    return 'PayPal is holding the payment. Here is the Readback.', lines


def approval_sent(name, threshold, total):
    return [f'This order totals {usd(total)}, which is over your approval amount of {usd(threshold)}.',
            f'Sent to {name} for approval. When {name} approves, say confirm and type your PIN. Say cancel to release the hold.',
            'In this prototype the approval link is shown here instead of emailed.']


def receipt(capture, order_id):
    return (f"Paid. PayPal captured {usd(capture['amount']['value'])}. Order number {order_id}. "
            'Say spell that to hear the order number letter by letter.')


def pin_wrong(left):
    return f"That PIN is not right. {left} {'try' if left == 1 else 'tries'} left."


def spell(text):
    words = [' '.join(ch.upper() if ch.isalpha() else ch for ch in w) for w in text.split()]
    return ', space, '.join(words)


def query_label(words, max_price=None, category=None):
    out = words or (category or 'everything')
    if words and category:
        out += f' in {category}'
    if max_price is not None:
        out += f' under {money(max_price)}'
    return out


def settings_summary(caps, mode, linked, pin_set, spent, prefs=None, contact=None):
    return (f"Per-order cap {usd(caps['order'])}. Daily cap {usd(caps['daily'])}, {usd(spent)} spent today. "
            f"Replies are read by {'your screen reader' if mode == 'screen_reader' else 'the app voice'}. "
            f"PayPal is {'linked' if linked else 'not linked'}. PIN is {'set' if pin_set else 'not set'}. "
            + (prefs_summary(prefs) if prefs else '')
            + (f"{contact['name']} approves orders over {usd(contact['threshold'])}. " if contact else '')
            + 'Caps, PIN and preferences can only be changed in the Settings form.')


def prefs_summary(p):
    out = f"Replies are {'simple, one result at a time' if p['simple'] else p['verbosity']}. "
    if p['size']:
        out += f"Default size {p['size']}. "
    if p['avoid']:
        out += f"Always avoiding {_ns(p['avoid']).replace(' or ', ' and ')} in food. "
    return out
