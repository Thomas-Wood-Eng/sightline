import json
import copy
import re

from app import catalog, lane1, speech


def prod(pid='hoodie-01'):
    return copy.deepcopy(catalog.get(pid))


def test_result_line_short_and_from_data():
    p = prod()
    p['name'] = 'An extremely long product name that goes on and on and on forever and ever'
    line = speech.result_line(1, p)
    assert len(line.split()) <= 15
    assert line.endswith(', $34.99, 4.6 stars')


def test_guard_drops_money_sentences():
    assert speech.guard('Soft and warm. Only $9.99 today! Great gift.') == 'Soft and warm. Great gift.'
    assert speech.guard('It costs 20 dollars.') == ''
    assert speech.guard('Has 2 pockets.') == 'Has 2 pockets.'


def test_llm_text_never_reaches_a_number_slot():
    """Enriched (LLM-written) text with a price in it must not be spoken; prices come only from catalogue fields."""
    p = prod()
    p['enriched']['description'] = 'A cosy hoodie. Yours for just $1.00!'
    p['enriched']['facts'].append({'label': 'deal', 'value': 'costs 5 dollars', 'source': 'photo'})
    text = ' '.join(speech.describe(p))
    assert '$1.00' not in text and '5 dollars' not in text
    assert re.findall(r'\$\d+\.\d\d', text) == ['$34.99', '$4.99']  # price and shipping, from data


def test_describe_labels_and_order():
    lines = speech.describe(prod())
    text = ' '.join(lines)
    assert 'Listing says:' in text and 'Photo suggests, unverified:' in text
    assert 'Allergens not stated' in text
    keys = ['size', 'Colour', 'Material', 'Condition', 'In the box', 'Allergens']
    pos = [lines[1].index(k) for k in keys]
    assert pos == sorted(pos)


def test_compare_is_deterministic():
    items = [(1, prod('hoodie-01')), (2, prod('sweater-01')), (3, prod('mug-01')), (4, prod('headphones-01'))]
    say, lines = speech.compare(items)
    assert say.startswith('Comparing 3 items')  # at most three
    assert lines[0] == 'Cheapest: number 3, Insulated travel mug, $18.50.'
    assert lines[1].startswith('Best rated: number 2') and '4.8 stars' in lines[1]


def test_readback_from_paypal_breakdown():
    order = {'purchase_units': [{'amount': {'currency_code': 'USD', 'value': '41.73', 'breakdown': {
        'item_total': {'value': '34.99'}, 'shipping': {'value': '4.99'}, 'tax_total': {'value': '1.75'}}},
        'items': [{'name': 'Hoodie', 'quantity': '1', 'unit_amount': {'value': '34.99'}}]}]}
    say, lines = speech.readback(order, {'delivery_days': 3, 'seller': 'Demo'})
    assert lines[:4] == ['Item 1: Hoodie. Quantity 1. Unit price 34.99 US dollars.', 'Shipping: 4.99 US dollars.',
                         'Tax: 1.75 US dollars.', 'Total: 41.73 US dollars.']


def test_cap_refusal_states_cap_and_overage():
    s = speech.cap_refusal('order', '100.00', '120.50')
    assert 'cap is 100.00 US dollars' in s and '20.50 US dollars over' in s


def test_spell():
    assert speech.spell('Ab 2') == 'A b, space, 2'.replace('b', 'B')


def test_search_filters():
    assert [p['id'] for p in catalog.search('hoodies')] == ['hoodie-01']
    assert all(p['price'] <= 40 for p in catalog.search('', max_price=40))
    assert {p['category'] for p in catalog.search('', category='clothing')} == {'clothing'}
    assert catalog.search('warm', max_price=20) == []
    assert catalog.search('zzzz') == []


def test_lane1_price_and_category_parsing():
    assert lane1.parse('warm hoodie under 40') == ('warm hoodie', 40.0, None)
    assert lane1.parse('something for the kitchen below $25') == ('', 25.0, 'kitchen')
    assert lane1.parse('clothes less than 60 dollars')[1:] == (60.0, 'clothing')


def test_lane1_handle_shows_at_most_three():
    s = {}
    r = lane1.handle('anything under 100', s)
    assert len(r.lines) <= 3 and r.say.startswith('4 results for everything under $100.00')


def test_lane1_context_never_contains_prices():
    s = {'results': [p['id'] for p in catalog.PRODUCTS[:3]], 'page': 0, 'focus': catalog.PRODUCTS[0]['id']}
    ctx = json.dumps(lane1.context(s))
    for p in catalog.PRODUCTS[:3]:
        assert f"{p['price']:.2f}" not in ctx and '"price"' not in ctx
    assert lane1.band(24.99) == 'under 25' and lane1.band(34.99) == '25 to 50'


def test_allergen_filter_is_strict():
    mk = lambda i, a: {'id': i, 'listing': {'allergens': a}}
    items = [mk('trail', 'Contains peanuts, almonds.'), mk('granola', 'May contain traces of tree nuts.'),
             mk('choc', 'Contains milk. May contain hazelnuts.'), mk('tea', 'No major allergens declared.'), mk('mystery', None)]
    safe, excluded = lane1.allergen_filter(items, ['nuts'])
    assert [p['id'] for p in safe] == ['tea'] and excluded == 4   # "may contain" and "not stated" are both excluded
    safe, _ = lane1.allergen_filter(items, ['milk'])
    assert 'choc' not in [p['id'] for p in safe] and 'mystery' not in [p['id'] for p in safe]
