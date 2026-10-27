"""Checkout state machine: idle -> readback_pending -> awaiting_confirm -> awaiting_pin -> captured | voided.

Deterministic and LLM-free: confirm, cancel and the PIN only ever reach this file.
Caps are checked here before any hold. One PayPal-Request-Id per checkout attempt makes repeats replay, not re-charge.
"""
import hashlib, hmac, os, secrets, uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from . import catalog, paypal, speech
from .speech import Reply

TAX_RATE = Decimal('0.05')  # flat demo rate
MAX_TRIES = 3
DEFAULT_CAPS = {'order': '100.00', 'daily': '250.00'}
IDLE, READBACK, CONFIRM, PIN, CAPTURED, VOIDED = 'idle', 'readback_pending', 'awaiting_confirm', 'awaiting_pin', 'captured', 'voided'
HOLDING = (CONFIRM, PIN)
LOCKED = ('Your PIN is locked after three wrong tries. Nothing was charged. '
          'To unlock, link PayPal again, which needs your PayPal login, then set a new PIN.')

# shortcut: PIN tries, lockout and today's spend live in server memory keyed by session id, so replaying an old
# signed cookie can't reset them; they are lost on restart. Move to a database before real money.
LEDGER = {}


def ledger(s):
    sid = s.setdefault('sid', uuid.uuid4().hex)
    led = LEDGER.setdefault(sid, {'tries': 0, 'locked': False, 'day': '', 'spent': Decimal(0), 'captured': set()})
    today = date.today().isoformat()
    if led['day'] != today:
        led.update(day=today, spent=Decimal(0))
    return led


def state(s):
    return s.get('co', {}).get('state', IDLE)


def caps(s):
    return {k: Decimal(v) for k, v in (s.get('caps') or DEFAULT_CAPS).items()}


def vault_id(s):
    # DEMO_VAULT_ID: optional pre-approved sandbox wallet for local testing / judges
    return s.get('vault_id') or os.environ.get('DEMO_VAULT_ID')


# ---- PIN -------------------------------------------------------------------------------------------------------
def valid_pin(pin):
    return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()


def _hash(pin, salt):
    # server secret as pepper: the hash sits in the client's cookie, so offline guessing needs the secret too
    return hashlib.scrypt((pin + os.environ.get('SESSION_SECRET', '')).encode(), salt=bytes.fromhex(salt),
                          n=2 ** 14, r=8, p=1).hex()


def set_pin(s, pin):
    salt = secrets.token_hex(16)
    s['pin'] = {'salt': salt, 'hash': _hash(pin, salt)}
    led = ledger(s)
    led.update(tries=0, locked=False)


def verify_pin(s, pin):
    """'ok' | 'wrong' | 'locked'. Wrong tries count toward the lockout wherever the PIN is asked for."""
    led, p = ledger(s), s.get('pin')
    if led['locked'] or not p:
        return 'locked' if led['locked'] else 'wrong'
    if valid_pin(pin) and hmac.compare_digest(_hash(pin, p['salt']), p['hash']):
        led['tries'] = 0
        return 'ok'
    led['tries'] += 1
    if led['tries'] >= MAX_TRIES:
        led['locked'] = True
        _void_quietly(s)
        return 'locked'
    return 'wrong'


def unlock(s):
    """Called after a fresh PayPal login: clears the lockout and the old PIN."""
    s.pop('pin', None)
    ledger(s).update(tries=0, locked=False)


# ---- money -----------------------------------------------------------------------------------------------------
def cart_lines(cart):
    """Stored cart [[id, qty, variant]] (older cookies lack the variant) -> [(product, qty, variant)]."""
    return [(catalog.get(l[0]), l[1], l[2] if len(l) > 2 else '') for l in cart if catalog.get(l[0])]


def totals(cart):
    lines = cart_lines(cart)
    items = [{'name': speech.item_name(p, v), 'quantity': q, 'unit_amount': Decimal(str(p['price']))} for p, q, v in lines]
    item_total = sum((i['unit_amount'] * i['quantity'] for i in items), Decimal(0))
    shipping = sum((Decimal(str(p['shipping'])) for p, _, _ in lines), Decimal(0))
    tax = (item_total * TAX_RATE).quantize(Decimal('0.01'), ROUND_HALF_UP)
    return items, shipping, tax, item_total + shipping + tax, lines


def start(s):
    st = state(s)
    if st in HOLDING:
        co = s['co']
        return Reply('A payment is already on hold. ' + co['say'], co['lines'])
    if not s.get('cart'):
        return Reply('Your cart is empty. Search for something and add it first.')
    led = ledger(s)
    if led['locked']:
        return Reply(LOCKED)
    if not s.get('pin'):
        return Reply('Set a PIN first, in the Setup form, before you can pay.')
    if not vault_id(s):
        return Reply('PayPal is not linked yet. Say link PayPal, or use the Link PayPal link on the page.')
    items, shipping, tax, total, lines = totals(s['cart'])
    c = caps(s)
    if total > c['order']:
        return Reply(speech.cap_refusal('order', c['order'], total))
    if led['spent'] + total > c['daily']:
        return Reply(speech.cap_refusal('daily', c['daily'], total, led['spent']))

    rid = uuid.uuid4().hex  # one id per checkout attempt; suffixes keep hold/capture/void distinct
    s['co'] = {'state': READBACK, 'rid': rid}
    try:
        order = paypal.create_hold(vault_id(s), items, shipping, tax, rid + '-hold')
        auth = order['purchase_units'][0]['payments']['authorizations'][0]
    except (paypal.PayPalError, KeyError, IndexError) as e:
        s['co'] = {'state': IDLE}
        return Reply(f'PayPal did not place the hold, so nothing was charged. {e}. Say check out to try again.')
    if Decimal(order['purchase_units'][0]['amount']['value']) != total or auth.get('status') != 'CREATED':
        _void(auth['id'], rid)
        s['co'] = {'state': VOIDED}
        return Reply("PayPal's hold did not match the cart, so I released it. Nothing was charged.")
    meta = {'delivery_days': max(p['delivery_days'] for p, _, _ in lines),
            'seller': ', '.join(sorted({p['seller'] for p, _, _ in lines}))}
    say, rb = speech.readback(order, meta)
    s['co'] = {'state': CONFIRM, 'rid': rid, 'order_id': order['id'], 'auth_id': auth['id'], 'say': say, 'lines': rb}
    return Reply(say, rb)


def confirm(s):
    st = state(s)
    if st == CONFIRM:
        s['co'] = {**s['co'], 'state': PIN}
        return Reply('Confirmed. Now type your 4-digit PIN in the PIN box and press Enter. Or say cancel.')
    if st == PIN:
        return Reply('Type your 4-digit PIN in the PIN box and press Enter. Or say cancel.')
    if st == CAPTURED:
        return Reply(f"Already paid, nothing more to confirm. Order number {s['co']['order_id']}.")
    return Reply('Nothing to confirm right now.')


def _void(auth_id, rid):
    return paypal.void(auth_id, rid + '-void')


def _void_quietly(s):
    if state(s) in HOLDING:
        try:
            _void(s['co']['auth_id'], s['co']['rid'])
        except paypal.PayPalError:
            pass  # an unreleased hold is never captured and expires on its own
        s['co'] = {'state': VOIDED}


def cancel(s):
    if state(s) not in HOLDING:
        return Reply('Nothing is on hold, so there is nothing to cancel.')
    try:
        _void(s['co']['auth_id'], s['co']['rid'])
    except paypal.PayPalError as e:
        return Reply(f'PayPal could not release the hold just now ({e}). Nothing was charged. Say cancel to try again.')
    s['co'] = {'state': VOIDED}
    return Reply('Cancelled. PayPal released the hold. Nothing was charged. Your cart is unchanged.')


def pin(s, entered):
    st = state(s)
    if st == CAPTURED:
        return Reply(f"Already paid. Order number {s['co']['order_id']}.")
    if st != PIN:
        return Reply('No payment is waiting for a PIN. Say check out first.')
    if not valid_pin(entered):
        return Reply('The PIN is 4 digits. Please type it again.')  # format slips don't count as tries
    result = verify_pin(s, entered)
    if result == 'locked':
        return Reply(LOCKED + ' The hold was released.')
    if result == 'wrong':
        return Reply(speech.pin_wrong(MAX_TRIES - ledger(s)['tries']))
    co = s['co']
    try:
        cap = paypal.capture(co['auth_id'], co['rid'] + '-capture')
    except paypal.PayPalError as e:
        return Reply(f'PayPal did not take the payment ({e}). Nothing was charged. '
                     'Type the PIN to try again, or say cancel.')
    led = ledger(s)
    if co['rid'] not in led['captured']:
        led['captured'].add(co['rid'])
        led['spent'] += Decimal(cap['amount']['value'])
    s['co'] = {'state': CAPTURED, 'order_id': co['order_id'], 'rid': co['rid']}
    s['cart'] = []
    s['spell'] = co['order_id']
    return Reply(speech.receipt(cap, co['order_id']))
