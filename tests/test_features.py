"""Tests for the post-MVP features (FEATURES.md)."""
from app import lane0
from app.lane0 import parse
from conftest import say
from test_checkout import setup, t


# ---- 1. sizes and variants ----
def test_parse_variants():
    assert parse('add it in medium') == ('add', 1, 'it', 'medium')
    assert parse('add number 2 in size L') == ('add', 1, ('n', 2), 'l')
    assert parse('add 2 of them in black') == ('add', 2, 'it', 'black')
    assert parse('the black one') == ('pick', ('name', 'black'))


def test_match_size():
    assert lane0.match_size('medium', ['S', 'M', 'L']) == 'M'
    assert lane0.match_size('extra large please', ['S', 'L', 'XL']) == 'XL'
    assert lane0.match_size('us nine', ['US 8', 'US 9']) == 'US 9'
    assert lane0.match_size('32 by 32', ['30x30', '32x32']) == '32x32'
    assert lane0.match_size('black', ['S', 'M']) is None


def test_add_asks_for_size_then_readback_has_it(client, fake):
    setup(client)
    t(client, 'hoodie')
    r = t(client, 'add it')
    assert r['say'].startswith('Which size?') and 'S, M, L or XL' in r['say']
    assert t(client, 'cart')['say'] == 'Your cart is empty.'
    t(client, 'add it')
    r = t(client, 'medium')
    assert 'Added: Fleece-lined pullover hoodie (size M, heather grey)' in r['say']
    assert '(size M, heather grey)' in ' '.join(t(client, 'cart')['lines'])
    rb = ' '.join(t(client, 'check out')['lines'])
    assert 'Item 1: Fleece-lined pullover hoodie (size M, heather grey).' in rb
    order = next(iter(fake.seen.values()))
    assert order['purchase_units'][0]['items'][0]['name'] == 'Fleece-lined pullover hoodie (size M, heather grey)'


def test_colour_choice(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, '1')
    assert t(client, 'the black one')['say'].startswith('Black chosen')
    assert '(size L, black)' in t(client, 'add it in large')['say']
    assert '(size S, navy blue)' in t(client, 'add the navy one in small')['say']
    assert '(size XL, heather grey), quantity 1. Cart has 3 items' in t(client, 'add it in extra large')['say']


def test_size_question_dropped_by_other_command(client, fake):
    setup(client)
    t(client, 'hoodie'); t(client, 'add it')
    assert t(client, 'cancel')['say'] == 'OK, not added.'
    t(client, 'add it')
    assert t(client, 'what is in my cart')['say'] == 'Your cart is empty.'
