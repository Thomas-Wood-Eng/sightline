"""Every user-facing sentence that contains a number is rendered here, from data, by template.

Inputs are catalogue records or PayPal responses; free text from an LLM only ever passes through guard(),
which drops any sentence that mentions money or a number-like price.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


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


# the model's own reply text, beyond money: it must never talk about prices (the app says them from data), never
# echo its instructions, and never claim to have saved or changed a setting (only the Settings form can)
LLM_DROP = re.compile(
    r"\b(?:prices?|priced|costs?|price bands?|tiers?|never say|instructions?|system prompt|context|heard_as|tools?)\b"
    r"|\b(?:noted|note of|saved|save|updated|update|changed|change|stored|remembered|remember|set|added|registered)\b"
    r"[^.!?]*\b(?:contacts?|pin|caps?|limits?|settings?|preferences?|allerg\w*|threshold|account)\b"
    r"|\b(?:contacts?|pin|caps?|limits?|settings?|preferences?|allerg\w*|threshold)\b[^.!?]*\b(?:noted|saved|updated|"
    r"changed|stored|remembered|set|added|registered)\b"
    r"|\b(?:app menu|account page|account settings|on (?:your|the) screen)\b", re.I)


def llm_text(text):
    """Every sentence of Lane 1 model text passes this: guard() plus LLM_DROP. Returns the safe remainder."""
    return ' '.join(s for s in re.split(r'(?<=[.!?])\s+', guard(text)) if s and not LLM_DROP.search(s))


def plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


def short_name(p, max_words=10):
    w = p['name'].split()
    return ' '.join(w[:max_words])


def result_line(n, p, level='normal'):
    """"1. Fleece-lined pullover hoodie, $34.99, 4.6 stars" (15 words or fewer at every verbosity level)."""
    if level == 'brief':  # brief is the default: name, price and rating stay (research requirement 3)
        return f"{n}. {short_name(p, 7)}, {money(p['price'])}, {p['rating']} stars"
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


def allergens(p):
    a = (p['listing'].get('allergens') or 'not stated').strip().rstrip('.')
    return f"{p['name']}: the listing says, allergens: {a}."


def price(p):
    """'How much is it?': the catalogue price, said by the app (the model never sees prices)."""
    ship = Decimal(str(p['shipping']))
    return (f"{p['name']} is {money(p['price'])}, " + (f"plus {money(ship)} shipping." if ship else 'with free shipping.')
            + ' Tax is added at checkout, and the Readback reads the exact total from PayPal.')


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
        first = re.split(r'(?<=[.!?])\s+', lines[0], maxsplit=2)  # the name and one sentence; "more" has the rest
        return [' '.join(first[:2]), *food, lines[-1], *risky]
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
    listed = (f"Rated {p['rating']} stars from {plural(p['review_count'], 'review')}, as listed. "
              if p.get('review_count') else '')
    return (f"{listed}Summary of {plural(len(stars), 'sample review')} written for this demo, averaging {avg} stars:",
            lines)


def _best(items, key, reverse=False):
    """items: [(n, product)]; returns the winners' numbers and the winning value."""
    vals = [key(p) for _, p in items]
    best = max(vals) if reverse else min(vals)
    return [n for (n, p), v in zip(items, vals) if v == best], best


def compare(items, level='brief'):
    """items: [(number, product)], at most 3. Only what differs, one attribute per line, computed here from the
    catalogue, never by an LLM. Food allergens are always said (safety). Price with shipping is said when it changes
    the winner, or above brief."""
    items = items[:3]
    name = lambda ns: ' and '.join(f"number {n}, {short_name(dict(items)[n], 4)}" for n in ns)
    tie = lambda ns: 'Tie: ' if len(ns) > 1 else ''
    out, winners = [], {}

    def line(label, key, fmt, reverse=False):
        if len({key(p) for _, p in items}) > 1:  # the same for all is not a difference
            ns, v = _best(items, key, reverse)
            winners[label] = ns
            out.append(f'{label}: {tie(ns)}{name(ns)}, {fmt(v)}.')

    line('Cheapest', lambda p: Decimal(str(p['price'])), money)
    line('Best rated', lambda p: p['rating'], lambda v: f'{v} stars', reverse=True)
    line('Most reviews', lambda p: p['review_count'], lambda v: plural(v, 'review'), reverse=True)
    with_ship = len(out)
    line('Lowest price with shipping', lambda p: Decimal(str(p['price'])) + Decimal(str(p['shipping'])), money)
    if level == 'brief' and winners.get('Lowest price with shipping') == winners.get('Cheapest'):
        out[with_ship:] = []
    line('Arrives first', lambda p: p['delivery_days'], delivery_date)
    sizes = [(n, p['listing'].get('sizes')) for n, p in items]
    if any(s for _, s in sizes) and len({tuple(s or []) for _, s in sizes}) > 1:
        out.append('Sizes: ' + '; '.join(f'number {n}, {_ns(s)}' for n, s in sizes) + '.')
    if any(p['category'] == 'grocery' for _, p in items):
        out.append('Allergens, listing says: ' + '; '.join(
            f"number {n}, {_ns(p['listing'].get('allergens')).rstrip('.')}" for n, p in items) + '.')
    if not out:
        return f'Comparing {plural(len(items), "item")}: they are the same on price, rating, reviews and delivery.', []
    return f'Comparing {plural(len(items), "item")}, only what differs.', out


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


def wishlist(lines_in, alerts=None):
    """lines_in: [(product, variant)]; alerts: {pid: {'target': ...}} price-drop alerts."""
    if not lines_in:
        return 'You have no saved items. Say save it for later about any item.', []
    alerts = alerts or {}
    lines = [f"{i}. {item_name(p, v)}, {money(p['price'])}."
             + (f" Alert at {money(alerts[p['id']]['target'])} or less." if p['id'] in alerts else '')
             for i, (p, v) in enumerate(lines_in, 1)]
    return f"You have {plural(len(lines), 'saved item')}. Say move number 1 to my cart, for example.", lines


def alert_set(p, target, asked_amount):
    now = money(p['price'])
    when = f"drops to {money(target)} or less" if asked_amount else f"gets cheaper than {now}"
    return f"OK. I will tell you once if {p['name']} {when}. It is {now} now, and it is in your saved items."


def alert_already(p, target):
    return f"{p['name']} is already {money(p['price'])}, at or under {money(target)}. Say add it to buy it."


def price_drop(p, target):
    return (f"Price drop: {p['name']} is now {money(p['price'])}, at or under your alert of {money(target)}. "
            f"Say move the {short_name(p, 3).lower()} to my cart to buy it.")


def removed(p, cart_count, variant=''):
    return f"Removed: {item_name(p, variant)}. Cart has {plural(cart_count, 'item')}."


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
        if p.get('gift_card'):
            out.append('Heads up: gift cards are a common scam payment. Real agencies never ask for them.')
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


PAY_IN_4 = (Decimal(30), Decimal(1500))  # PayPal Pay in 4's US purchase range


def pay_in_4(total):
    """One Readback line. PayPal sets the real split; when 4 doesn't divide the total evenly we say "about"."""
    total = Decimal(str(total))
    part = (total / 4).quantize(Decimal('0.01'), ROUND_HALF_UP)
    return (f"PayPal Pay in 4 may be available: 4 payments of {'' if part * 4 == total else 'about '}{usd(part)}. "
            'Say pay later to hear more.')


def pay_later():
    """'pay later': plain words. Sightline never picks credit, by default or by the model."""
    return ('PayPal Pay in 4 splits a purchase into 4 interest-free payments: the first when you buy, then one every '
            "2 weeks. PayPal checks whether you are eligible, and you approve it on PayPal's own page. "
            'In this prototype Pay Later is chosen on PayPal\'s page; Sightline pays in full from your saved PayPal. '
            'Sightline never picks credit for you.')


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
              # gift note as PayPal holds it (PayPal fills in a description of its own when we send none)
              *([pu['description'].rstrip('.') + '.'] if meta.get('gift') and pu.get('description') else []),
              *meta.get('warnings', []),
              *([pay_in_4(amt['value'])] if PAY_IN_4[0] <= Decimal(amt['value']) <= PAY_IN_4[1] else []),
              'Say confirm to continue to your PIN, or cancel to release the hold.']
    return 'PayPal is holding the payment. Here is the Readback.', lines


SCAM_ADVICE = ('Real agencies, banks and police never ask for gift cards, wire transfers or crypto. '
               'They never ask you to keep it secret.')


def _scam_then(contact):
    """What happens to a payment Sightline suspects: the shopper's own choice in Settings (no contact: none goes ahead)."""
    if not contact:
        return 'A payment like this goes ahead only if your trusted contact approves it.'
    if contact.get('scam_hold', True):
        return f"Because you chose it in Settings, your next payment goes ahead only if {contact['name']} approves it."
    return 'Take a moment before you confirm.'


def scam_warning(contact):
    """Pressure words heard (Lane 0 scam guard): calm, short, no lecture."""
    return ('This matches a common scam. ' + SCAM_ADVICE + f' {_scam_then(contact)} It is OK to hang up and call someone '
            'you trust.' + ('' if contact else ' You have no trusted contact yet. You can add one in Settings.'))


def gift_card_note(contact):
    return ('A note first: gift cards are the most common way scammers ask to be paid. Real agencies never ask for '
            f'gift cards. {_scam_then(contact)}')


def scam_no_contact():
    return ('Not placed. Gift card orders, and orders after a scam warning, need a trusted contact to approve them. '
            'You have none yet. To add one, open Settings, fill in Trusted contact, and save with your PIN. '
            'Nothing was charged.')


def approval_sent(name, threshold, total, why=None):
    """Nothing is sent in this prototype: the shopper shares the link, so we never say "sent"."""
    first = (f"This order needs {name}'s approval: Sightline flagged it as a possible gift-card scam." if why else
             f'This order totals {usd(total)}, which is over your approval amount of {usd(threshold)}.')
    return [first,
            f'Approval link ready for {name}. This prototype does not send it: share the link below with {name}. '
            f'When {name} approves, say confirm and type your PIN. Say cancel to release the hold.']


def _what(o):
    names = [l['name'] for l in o['lines']]
    return names[0] + (f", and {plural(len(names) - 1, 'more item')}" if len(names) > 1 else '') if names else 'an order'


def _day(iso):
    d = datetime.fromisoformat(iso)
    return f'{d:%A, %B} {d.day}'


def orders(rows):
    """Order history from our ledger, newest first, at most three."""
    if not rows:
        return 'You have no orders yet.', []
    lines = []
    for i, o in enumerate(rows[:3], 1):
        ref = sum((Decimal(l['refunded']) for l in o['lines']), Decimal(0))
        lines.append(f"{i}. {_day(o['created'])}: {_what(o)}. Paid {usd(o['total'])}"
                     + (f", {usd(ref)} refunded." if ref else '.'))
    lead = f"You have {plural(len(rows), 'order')}." + (' The latest three:' if len(rows) > 3 else '')
    return lead, lines + ['Say where is my order, return an item, or reorder the last thing.']


def track(o, status):
    """status: PayPal's order status. Delivery is estimated from the catalogue's delivery time, not tracked."""
    created = datetime.fromisoformat(o['created']).date()
    return (f"Your order of {_what(o)}, placed {_day(o['created'])}: PayPal shows it as {status.lower()}. "
            f"Estimated delivery {delivery_date(o['delivery_days'], created)}, from the store's usual delivery time. "
            f"Order number {o['order_id']}.")


def spending(period, amount, n):
    label = {'today': 'Today', 'week': 'This week, since Monday', 'month': 'This month', 'last_week': 'Last week',
             'last_month': 'Last month', 'all': 'In total'}[period]
    return f"{label}, you spent {usd(amount)} on {plural(n, 'order')}, after refunds."


def purchases(rows, most=5):
    """'What did I buy last month?': items, dates and totals from our ledger (PayPal's ids and amounts), newest first."""
    lines = []
    for o in rows[:most]:
        ref = sum((Decimal(l['refunded']) for l in o['lines']), Decimal(0))
        lines.append(f"{_day(o['created'])}: {', '.join(l['name'] for l in o['lines'])}. Paid {usd(o['total'])}"
                     + (f", {usd(ref)} refunded" if ref else '') + f". PayPal order {o['order_id']}.")
    if len(rows) > most:
        lines.append(f"And {plural(len(rows) - most, 'older order')}. Say my orders to hear the latest ones.")
    return lines


def package_check(verdict, ordered, seen=''):
    """'Is this my package?': always "photo suggests", never certain. ordered: the order's item names with colour."""
    what = _ns(ordered).replace(' or ', ' and ')
    seen = seen.strip().rstrip('.')
    if seen[:2] in ('A ', 'An') or seen[:4] == 'The ':   # model text mid-sentence: "looks like a mug", not "like A mug"
        seen = seen[0].lower() + seen[1:]
    if verdict == 'yes':
        return f'Photo suggests this matches: {what}. A photo check can be wrong, so feel or open it to be sure.'
    if verdict == 'no':
        return (f'Photo suggests this may not match: you ordered {what}, the photo looks like {seen or "something else"}. '
                'Say return it to start a return.')
    if verdict == 'unsure':
        return (f'The photo is unclear: I could not tell whether it shows {what}. Try another photo in good light, '
                'with the item out of the box.')
    return (f'I could not check the photo just now, and nothing was kept. You ordered {what}. '
            'Try again in a minute, or ask someone you trust to look.')


def protection(kind):
    """Dispute help, 3 short sentences. kind: missing | broken | wrong."""
    first = {'missing': "Sorry it has not arrived. PayPal Purchase Protection covers eligible purchases that never arrive.",
             'broken': 'Sorry it arrived broken. PayPal Purchase Protection covers eligible items that arrive damaged '
                       'or significantly not as described.',
             'wrong': 'Sorry about that. PayPal Purchase Protection covers eligible items that are significantly not as '
                      'described, like the wrong item.'}[kind]
    return (f"{first} You can open a dispute in PayPal's Resolution Center within 180 days of paying. "
            'In this demo store, I can refund it for you now.')


def offer_refund(o, line):
    return (f"Do you want a refund for {line['name']}, from your order of {_day(o['created'])}? "
            'Say yes to hear the refund Readback, or no.')


def refund_readback(o, line, amount):
    """Amounts from our ledger, which holds PayPal's own unit prices and capture total."""
    item = Decimal(line['unit']) * line['qty']
    return ('Here is the return Readback.',
            [f"Return: {line['name']}. Quantity {line['qty']}. From order {o['order_id']}, placed {_day(o['created'])}.",
             f"Refund: {usd(amount)}. That is the item, {usd(item)}, plus its tax, {usd(line['tax'])}. Shipping is not refunded.",
             'The money goes back to your PayPal account.',
             'Say confirm to continue to your PIN, or cancel to keep the item.'])


def refunded(refund):
    return (f"Refunded {usd(refund['amount']['value'])} to your PayPal. PayPal says the refund is "
            f"{refund.get('status', 'pending').lower()}.")


def receipt(capture, order_id):
    return (f"Paid. PayPal captured {usd(capture['amount']['value'])}. Order number {order_id}. "
            'Say spell that to hear the order number letter by letter.')


def pin_wrong(left):
    return f"That PIN is not right. {left} {'try' if left == 1 else 'tries'} left."


def spell(text):
    words = [' '.join(ch.upper() if ch.isalpha() else ch for ch in w) for w in text.split()]
    return ', space, '.join(words)


def none_under(words, max_price, nearest):
    return (f"No {words} under {money(max_price)}. The closest is {nearest['name']}, {money(nearest['price'])}. "
            'Here are the matches without the price limit, cheapest first.')


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
            + (f"{contact['name']} approves orders over {usd(contact['threshold'])}"
               + (', and orders Sightline flags as a possible scam. ' if contact.get('scam_hold', True) else
                  f"; orders flagged as a possible scam do not wait for {contact['name']}. ") if contact else
               'No trusted contact is set. ')
            + 'Caps, PIN and preferences can only be changed in the Settings form.')


def prefs_summary(p):
    out = f"Replies are {'simple, one result at a time' if p['simple'] else p['verbosity']}. "
    if p['size']:
        out += f"Default size {p['size']}. "
    if p['avoid']:
        out += f"Always avoiding {_ns(p['avoid']).replace(' or ', ' and ')} in food. "
    return out


def saved(before, after, new_pin=False):
    """Settings save: only what changed, 15 words or fewer (the full summary is one "settings" away)."""
    b, a, bp, ap = before, after, before['prefs'], after['prefs']
    ch = []
    if a['output_mode'] != b['output_mode']:
        ch.append('the app voice reads replies' if a['output_mode'] == 'voice' else 'your screen reader reads replies')
    if ap['verbosity'] != bp['verbosity']:
        ch.append(f"{ap['verbosity']} replies")
    for key, label in (('simple', 'simple mode'), ('large_text', 'large text')):
        if ap[key] != bp[key]:
            ch.append(f"{label} {'on' if ap[key] else 'off'}")
    if ap['size'] != bp['size']:
        ch.append(f"default size {ap['size']}" if ap['size'] else 'no default size')
    if ap['avoid'] != bp['avoid']:
        ch.append('avoiding ' + _ns(ap['avoid']).replace(' or ', ' and ') if ap['avoid'] else 'no allergens avoided')
    if a['per_order_cap'] != b['per_order_cap']:
        ch.append(f"per-order cap {usd(a['per_order_cap'])}")
    if a['daily_cap'] != b['daily_cap']:
        ch.append(f"daily cap {usd(a['daily_cap'])}")
    if a['contact'] != b['contact']:
        c, old = a['contact'], b['contact'] or {}
        if c and {**old, 'scam_hold': c['scam_hold']} == c:  # only the scam choice changed
            ch.append(f"{c['name']} {'asked' if c['scam_hold'] else 'not asked'} when a scam is suspected")
        else:
            ch.append(f"{c['name']} approves orders over {usd(c['threshold'])}" if c else 'no trusted contact')
    if new_pin:
        ch.append('new PIN set')
    if not ch:
        return 'Settings saved: nothing changed.'
    text = 'Settings saved: ' + '; '.join(ch) + '.'
    return text if len(text.split()) <= 15 else f"Settings saved: {plural(len(ch), 'change')}. Say settings to hear them all."
