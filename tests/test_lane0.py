import pytest

from app.lane0 import parse

CASES = [
    ('next', ('next',)), ('Next one.', ('next',)), ('go back', ('back',)), ('previous', ('back',)),
    ('repeat', ('repeat',)), ('say that again', ('repeat',)), ('Pardon?', ('repeat',)),
    ('more', ('more', False)), ('tell me more', ('more', False)), ('more results', ('more', True)),
    ('spell that', ('spell',)), ('spell the order number', ('spell',)),
    ('add it', ('add', 1, 'it')), ('add to cart', ('add', 1, 'it')), ('add this one to my cart', ('add', 1, 'it')),
    ('add number 2', ('add', 1, ('n', 2))), ('add the second one', ('add', 1, ('n', 2))), ('add two', ('add', 1, ('n', 2))),
    ('add two of them', ('add', 2, 'it')), ('add 3 of number 1', ('add', 3, ('n', 1))),
    ('add a hoodie to my cart', ('add', 1, ('name', 'hoodie'))), ('add 2 hoodies', ('add', 2, ('name', 'hoodies'))),
    ("I'll take number 3", ('add', 1, ('n', 3))), ('please add it, thanks', ('add', 1, 'it')),
    ('remove it', ('remove', 'it')), ('remove number 1 from my cart', ('remove', ('n', 1))), ('take it out', ('remove', 'it')),
    ("what's in my cart", ('cart',)), ('cart', ('cart',)), ('show my basket', ('cart',)), ('empty the cart', ('clear',)),
    ('check out', ('checkout',)), ('checkout', ('checkout',)), ("I'd like to check out please", ('checkout',)),
    ('place my order', ('checkout',)),
    ('confirm', ('confirm',)), ('Confirm.', ('confirm',)), ('I confirm the purchase', ('confirm',)),
    ('cancel', ('cancel',)), ('cancel the order', ('cancel',)), ('never mind', ('cancel',)),
    ('yes', ('yes',)), ('yeah', ('yes',)), ('no', ('no',)), ('nope', ('no',)),
    ('2', ('pick', 2)), ('number three', ('pick', 3)), ('the first one', ('pick', 1)), ('the last one', ('pick', -1)),
    ('help', ('help',)), ('what can I do', ('help',)), ('what are my options', ('help',)),
    ('describe it', ('describe', 'it')), ('describe number 2', ('describe', ('n', 2))),
    ('tell me about the second one', ('describe', ('n', 2))), ('what does it look like', ('describe', 'it')),
    ('compare them', ('compare', [])), ('compare 1 and 3', ('compare', [1, 3])), ('compare the first two', ('compare', [1, 2])),
    ('which is cheaper', ('compare', [])),
    ('settings', ('settings',)), ('link my PayPal', ('link',)), ('connect paypal account', ('link',)),
    ("that's wrong", ('wrong',)), ('That is not right', ('wrong',)), ('wrong', ('wrong',)),
    # caps can never be changed by voice
    ('raise my cap to 500', ('caps',)), ('set my daily limit to 1000 dollars', ('caps',)), ('what is my limit', ('settings',)),
]


@pytest.mark.parametrize('text,expected', CASES)
def test_parse(text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize('text', ['warm hoodie under 40', 'buy a gift for my mum', 'something for the kitchen',
                                  'i want a hoodie', 'find me headphones', 'is it machine washable'])
def test_free_text_goes_to_lane1(text):
    assert parse(text) is None
