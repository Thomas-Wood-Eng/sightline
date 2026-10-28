"""Lane 1: free-form requests. Interface: handle(text, session) -> Reply.

One Gemini call per turn (app/llm.py): the model either calls search_products (results are rendered by speech.py
templates) or answers a question about the products in context (its text goes through speech.guard()).
It never sees a price, only a band. If the model is slow, down, or says nothing usable, the keyword search answers.
"""
import json
import os
import re

from . import catalog, llm, speech
from .lane0 import _results, card, prefs, show_results
from .speech import Reply

PRICE_RE = re.compile(r'\b(?:under|below|less than|cheaper than|max(?:imum)?|up to|at most|no more than|within)'
                      r'\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars?|bucks|usd)?', re.I)
SYNONYMS = {'clothes': 'clothing', 'clothe': 'clothing', 'apparel': 'clothing', 'gift': 'gifts', 'present': 'gifts',
            'food': 'grocery', 'grocerie': 'grocery', 'snack': 'grocery', 'tech': 'electronics', 'gadget': 'electronics',
            'cooking': 'kitchen', 'house': 'home'}


def parse(text):
    """-> (query words, max_price or None, category or None)"""
    m = PRICE_RE.search(text)
    max_price = float(m.group(1)) if m else None
    rest = PRICE_RE.sub(' ', text) if m else text
    category = None
    for w in catalog.tokens(rest):
        c = SYNONYMS.get(w, w)
        if c in catalog.CATEGORIES or c + 's' in catalog.CATEGORIES:
            category = c if c in catalog.CATEGORIES else c + 's'
    is_cat = lambda w: category and SYNONYMS.get(w, w).rstrip('s') == category.rstrip('s')
    words = ' '.join(w for w in re.findall(r'[a-z0-9]+', rest.lower())
                     if w not in catalog.STOP and not is_cat(w) and not is_cat(catalog.tokens(w)[0]))
    return words, max_price, category


def keyword(text, session):
    """No-AI fallback: keyword search with naive price parsing ("under 40")."""
    words, max_price, category = parse(text)
    products = catalog.search(words, max_price, category)
    if not products and words and (max_price is not None or category):
        products = catalog.search('', max_price, category)  # filter matched but words didn't: show the filter
        words = ''
    products, note = saved_filter(session, products)
    return noted(show_results(session, products, speech.query_label(words, max_price, category)), note)


def saved_filter(session, products):
    """Allergens from Settings: a hard filter on every search. Food (or anything listing allergens) must declare
    none of them; other items stay. Returns (products, short note or '')."""
    avoid = prefs(session)['avoid']
    food = [p for p in products if p['category'] == 'grocery' or p['listing'].get('allergens')]
    if not avoid or not food:
        return products, ''
    safe, excluded = allergen_filter(food, avoid)
    note = f"From your settings: food only if its listing declares no {', '.join(avoid)}."
    if excluded:
        note += f" {speech.plural(excluded, 'item')} left out."
    return [p for p in products if p not in food or p in safe], note


def noted(reply, note):
    if note:
        reply.say = f'{note} {reply.say}'  # say + lines are both spoken: the note goes in one place only
    return reply


SYSTEM = """You are Sightline, a voice shopping assistant for blind and low-vision people.
Your words are read aloud by a screen reader: one or two short plain sentences, no lists, no markdown, no emoji.
- To find products, call search_products. If the shopper mentions an allergy, pass it in avoid_allergens. Never describe products that are not in CONTEXT.
- "The first one", "number two" etc. mean the product whose heard_as is "result 1", "result 2"; "it" means the focused one.
- To answer a question about products in CONTEXT, use only their facts. Say "the listing says" for listing facts and
  "the photo suggests" for photo facts. If a fact is not given, say it is not stated. Never guess size, fit, allergens
  or dimensions.
- Never say a price, cost, total or any amount of money. The app reads prices itself.
- You cannot add to cart, buy, or change settings. If asked, tell the user to say "add it" or "check out"."""

TOOLS = [{
    'name': 'search_products',
    'description': "Search the store catalogue. Use the shopper's own words for query.",
    'parameters': {'type': 'object', 'properties': {
        'query': {'type': 'string', 'description': 'what to look for, e.g. "warm hoodie"; empty to browse a category'},
        'max_price': {'type': 'number', 'description': 'only if the shopper gave a budget, in US dollars'},
        'category': {'type': 'string', 'enum': catalog.CATEGORIES},
        'avoid_allergens': {'type': 'array', 'items': {'type': 'string'},
                            'description': 'allergens the shopper must avoid, e.g. ["nuts"]; never put these in query'}},
        'required': ['query']}}]


def band(price):
    return next(b for limit, b in ((25, 'under 25'), (50, '25 to 50'), (100, '50 to 100'), (1e9, 'over 100')) if price < limit)


def facts(p):
    """What the model may know about a product: no price fields, every fact tagged with its source."""
    e = p.get('enriched') or {}
    listing = {k: v for k, v in p['listing'].items() if v not in (None, '', [])}
    return {'id': p['id'], 'name': p['name'], 'category': p['category'], 'price_band': band(p['price']),
            'rating': p['rating'], 'reviews': p['review_count'],
            'facts': e.get('facts') or [{'label': k, 'value': v, 'source': 'listing'} for k, v in listing.items()],
            'qa': e.get('qa', [])}


def context(session):
    """The focused product plus the results the shopper just heard, so "is it warm?" or "which is softer?" works."""
    focus = catalog.get(session.get('focus') or '')
    page = session.get('page', 0)  # an index into the results, not a page number
    shown = _results(session)[page: page + 3]
    items = [dict(facts(p), heard_as=f'result {n}') for n, p in enumerate(shown, page + 1)]
    for item in items:
        item['focused'] = focus is not None and item['id'] == focus['id']
    if focus and not any(i['focused'] for i in items):
        items.insert(0, dict(facts(focus), heard_as='the item in focus', focused=True))
    return items


ALLERGY = re.compile(r'allerg|\bnuts?\b|peanut|gluten|wheat|dairy|lactose|milk|\bsoy\b|\begg|shellfish|sesame', re.I)
# words that, in a listing's allergen text, mean the product is unsafe for someone avoiding the key
ALLERGEN_WORDS = {'nut': r'nut|peanut|almond|cashew|hazelnut|walnut|pecan|pistachio|macadamia',
                  'gluten': r'gluten|wheat|barley|rye|oat', 'wheat': r'wheat|gluten', 'milk': r'milk|dairy|lactose|whey|butter|cream',
                  'dairy': r'milk|dairy|lactose|whey|butter|cream', 'lactose': r'milk|dairy|lactose|whey', 'soy': r'soy',
                  'egg': r'\begg', 'sesame': r'sesame', 'shellfish': r'shellfish|shrimp|crab|lobster', 'fish': r'\bfish'}


def canon(allergen):
    """'peanuts', 'tree nuts', 'almonds' -> 'nuts'; unknown words pass through."""
    key = next((k for k, pat in ALLERGEN_WORDS.items() if re.search(pat, allergen, re.I)), None)
    return {'nut': 'nuts', 'egg': 'eggs'}.get(key, key) if key else allergen


def allergen_filter(products, avoid):
    """Keep only products whose listing states allergens and mentions none of `avoid` (incl. "may contain").
    Unknown allergens count as unsafe: we never guess. Returns (safe, excluded_count)."""
    pats = [ALLERGEN_WORDS.get(a.lower().rstrip('s'), re.escape(a.lower().rstrip('s'))) for a in avoid]
    unsafe = lambda p: not p['listing'].get('allergens') or any(re.search(x, p['listing']['allergens'], re.I) for x in pats)
    safe = [p for p in products if not unsafe(p)]
    return safe, len(products) - len(safe)


def with_allergens(reply, products):
    """Allergy mentioned: state each spoken result's allergens straight from the listing, never from the model."""
    notes = [f"Result {n}: allergens {(p['listing'].get('allergens') or 'not stated').rstrip('.')}."
             for n, p in enumerate(products[:3], 1)]
    reply.lines = [*reply.lines, *notes]  # detail lines only; repeating them in say would be spoken twice
    return reply


PACKAGE = """A blind shopper photographed what was delivered. Compare the photo with what they ordered.
ORDERED (name, colour, and what the store's own photo shows):
{items}
Answer JSON only: {{"match": "yes" or "no" or "unsure", "item": "the ordered name the photo fits, or empty",
"seen": "what the photo shows, at most 10 words, no numbers"}}.
"yes" only if the photo plausibly shows an ordered item in its stated colour. "unsure" if the photo is blurry, dark,
or shows only a closed box or label."""


def _ordered(o):
    """[(ledger line, spoken name with colour, catalogue photo description)] for an order."""
    out = []
    for l in o['lines']:
        p = catalog.get(l['pid']) or {'listing': {}}
        colour = p['listing'].get('colour')
        name = l['name'] + (f', {colour}' if colour and not p.get('colours') else '')  # colour variants are in the name
        out.append((l, name, (p.get('enriched') or {}).get('description') or p['listing'].get('description') or ''))
    return out


def package_check(session, order, image, mime):
    """'Is this my package?': the photo and the order's names, colours and catalogue photo descriptions go to the
    model; the reply is built here from our order data, always as "photo suggests"."""
    items = _ordered(order)
    text = None
    if not os.environ.get('SIGHTLINE_NO_LLM'):
        text = llm.vision(PACKAGE.format(items='\n'.join(f'- {n}. {d}' for _, n, d in items)), image, mime)
    try:
        ans = json.loads(re.search(r'\{.*\}', text or '', re.S).group())
    except (AttributeError, ValueError):
        ans = {}
    verdict = ans.get('match') if ans.get('match') in ('yes', 'no', 'unsure') else None
    words = set(catalog.tokens(str(ans.get('item') or '')))
    best = max(items, key=lambda i: len(words & set(catalog.tokens(i[1]))))
    seen = ' '.join(speech.guard(str(ans.get('seen') or '')).rstrip('.').split()[:12])
    p = catalog.get(best[0]['pid'])
    if p:
        session['focus'], session['spell'] = p['id'], p['name']  # so "return it" means this item
    say = speech.package_check(verdict, [best[1]] if verdict == 'yes' else [n for _, n, _ in items], seen)
    return Reply(say, focus=card(p) if p else None)


def handle(text, session):
    if os.environ.get('SIGHTLINE_NO_LLM'):
        return keyword(text, session)
    ctx = context(session)
    prompt = f'CONTEXT (products the shopper has heard about):\n{json.dumps(ctx)}\n\nSHOPPER: {text}'
    out = llm.chat(SYSTEM, prompt, TOOLS)
    if out is None:
        return keyword(text, session)  # model slow or down: never leave the shopper waiting
    for name, args in out['calls']:
        if name == 'search_products':
            query = str(args.get('query') or '')
            try:
                max_price = float(args['max_price']) if args.get('max_price') else None
            except (TypeError, ValueError):
                max_price = None
            category = args.get('category') if args.get('category') in catalog.CATEGORIES else None
            avoid = [str(a) for a in args.get('avoid_allergens') or [] if str(a).strip()]
            # backstop: an allergen the shopper names is always filtered, even if the model forgot to pass it
            avoid += [w for w in ALLERGEN_WORDS if re.search(rf'\b{w}', text, re.I) and not any(w in a.lower() for a in avoid)]
            if avoid:  # an allergen word in the query would match the very products to avoid
                query = ' '.join(w for w in query.split()
                                 if w.lower() not in ('free', 'allergy', 'allergic') and not any(a.lower().rstrip('s') in w.lower() for a in avoid))
            products = catalog.search(query, max_price, category, limit=40)
            if not products and query and (max_price is not None or category):
                products, query = catalog.search('', max_price, category, limit=40), ''
            if not products and avoid and 'grocery' in catalog.CATEGORIES:  # "a snack, nut allergy": browse the food aisle
                products, query, category = catalog.search('', max_price, 'grocery', limit=40), '', 'grocery'
            excluded = 0
            if avoid:
                products, excluded = allergen_filter(products, avoid)
            products, saved_note = saved_filter(session, products)
            reply = noted(show_results(session, products, speech.query_label(query, max_price, category)), saved_note)
            if avoid and (products or excluded):
                named = list(dict.fromkeys(canon(a) for a in avoid))  # "nuts", not the model's list of every nut
                note = f"Showing only items whose listing declares no {', '.join(named)}."
                if excluded:
                    note += (f" {speech.plural(excluded, 'item')} left out because the listing contains, may contain,"
                             f" or does not state it.")
                reply.say = f'{note} {reply.say}'
            return with_allergens(reply, products) if ALLERGY.search(text) else reply
    say = speech.llm_text(out['text'] or '')
    return Reply(say) if say else keyword(text, session)
