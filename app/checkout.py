"""Checkout state machine: idle -> readback_pending -> awaiting_confirm -> awaiting_pin -> captured | voided.

Deterministic and LLM-free: confirm, cancel and the PIN only ever reach this file.
Caps are checked here before any hold. One PayPal-Request-Id per checkout attempt makes repeats replay, not re-charge.
"""
import hashlib, hmac, os, secrets, threading, time, uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from itsdangerous import URLSafeSerializer

from . import catalog, db, paypal, speech
from .speech import Reply

TAX_RATE = Decimal('0.05')  # flat demo rate
MAX_TRIES = 3
DEFAULT_CAPS = {'order': '100.00', 'daily': '250.00'}
IDLE, READBACK, CONFIRM, PIN, CAPTURED, VOIDED = 'idle', 'readback_pending', 'awaiting_confirm', 'awaiting_pin', 'captured', 'voided'
UNDO = 'undo_window'  # PIN accepted, capture waits a few seconds so "undo" can still void the hold
APPROVAL = 'awaiting_approval'  # over the trusted contact's threshold: held until they approve or decline
HOLDING = (CONFIRM, PIN, APPROVAL)
LOCKED = ('Your PIN is locked after three wrong tries. Nothing was charged. To unlock it: say link PayPal, or use the '
          '"Link PayPal again" link in the PayPal section of this page. Log in to PayPal; you then come back here, and '
          'the Setup form asks you to choose a new PIN.')

# shortcut: PIN tries, lockout and undone holds live in server memory keyed by session id, so replaying an old
# signed cookie can't reset them; they are lost on restart. Captured orders (and so today's spend) are in SQLite (db.py).
LEDGER = {}
_lock = threading.RLock()  # undo and capture of one hold never both go ahead
# shortcut: approval requests live in memory (lost on restart, the hold then just expires); move to SQLite before real use
APPROVALS = {}


def signer():
    return URLSafeSerializer(os.environ['SESSION_SECRET'], salt='approve')


def ledger(s):
    sid = s.setdefault('sid', uuid.uuid4().hex)
    return LEDGER.setdefault(sid, {'tries': 0, 'locked': False, 'undone': set()})


def spent_today(s):
    ledger(s)  # makes sure the session has an id
    return db.spent(s['sid'], date.today().isoformat())[0]


def state(s):
    co = s.get('co', {})
    if co.get('kind') == 'refund' and co.get('state') in HOLDING:
        o = db.get(co['order_id'])
        if o and o['lines'][co['line']]['refunded'] != '0.00':  # done by a request whose reply never arrived
            s['co'] = co = {'state': IDLE}
    return co.get('state', IDLE)


def caps(s):
    return {k: Decimal(v) for k, v in (s.get('caps') or DEFAULT_CAPS).items()}


def vault_id(s):
    # DEMO_VAULT_ID: optional pre-approved sandbox wallet for local testing / judges
    return s.get('vault_id') or os.environ.get('DEMO_VAULT_ID')


# ---- PIN -------------------------------------------------------------------------------------------------------
def valid_pin(pin):
    return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()


def _hash(pin, salt):
    # server secret as pepper: a leaked session row alone is not enough for offline guessing
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
    if spent_today(s) + total > c['daily']:
        return Reply(speech.cap_refusal('daily', c['daily'], total, spent_today(s)))

    rid = uuid.uuid4().hex  # one id per checkout attempt; suffixes keep hold/capture/void distinct
    s['co'] = {'state': READBACK, 'rid': rid}
    try:
        gift = s.get('gift')  # None: not a gift; '' : a gift with no note
        desc = None if gift is None else (f'Gift note: {gift}' if gift else 'This is a gift, with no note')
        order = paypal.create_hold(vault_id(s), items, shipping, tax, rid + '-hold', desc)
        auth = order['purchase_units'][0]['payments']['authorizations'][0]
    except (paypal.PayPalError, KeyError, IndexError) as e:
        s['co'] = {'state': IDLE}
        return Reply(f'PayPal did not place the hold, so nothing was charged. {e}. Say check out to try again.')
    if Decimal(order['purchase_units'][0]['amount']['value']) != total or auth.get('status') != 'CREATED':
        _void(auth['id'], rid)
        s['co'] = {'state': VOIDED}
        return Reply("PayPal's hold did not match the cart, so I released it. Nothing was charged.")
    meta = {'delivery_days': max(p['delivery_days'] for p, _, _ in lines),
            'seller': ', '.join(sorted({p['seller'] for p, _, _ in lines})), 'warnings': speech.warnings(lines),
            'gift': bool(desc)}
    say, rb = speech.readback(order, meta)
    s['co'] = {'state': CONFIRM, 'rid': rid, 'order_id': order['id'], 'auth_id': auth['id'], 'say': say, 'lines': rb,
               'pay': f"Paying {speech.usd(order['purchase_units'][0]['amount']['value'])} to {meta['seller']}",
               'days': meta['delivery_days'],  # for the ledger: our ids beside PayPal's item names and unit prices
               'items': [[p['id'], it['name'], q, it['unit_amount']['value']]
                         for (p, q, _), it in zip(lines, order['purchase_units'][0].get('items', []))]}
    contact = s.get('contact')
    if contact and total > Decimal(contact['threshold']):
        aid = secrets.token_urlsafe(16)
        APPROVALS[aid] = {'state': 'pending', 'name': contact['name'], 'lines': rb[:-1], 'auth_id': auth['id'], 'rid': rid}
        link = '/approve/' + signer().dumps(aid)
        rb = rb[:-1] + speech.approval_sent(contact['name'], contact['threshold'], total) + [f'Approval link: {link}']
        s['co'].update(state=APPROVAL, approval=aid, lines=rb)
    return Reply(say, rb)


def approval_news(s):
    """Shopper side: has the trusted contact decided? Returns a Reply when something changed."""
    a = APPROVALS.get(s['co'].get('approval'))
    if a is None:
        return Reply('The approval request was lost when the app restarted. Say cancel to release the hold, '
                     'then check out again.')
    if a['state'] == 'approved':
        say = f"{a['name']} approved this order. Say confirm to continue to your PIN, or say cancel."
        s['co'].update(state=CONFIRM, say=say, lines=a['lines'])
        return Reply(say, s['co']['lines'])
    if a['state'] == 'declined':
        s['co'] = {'state': VOIDED}
        return Reply(f"{a['name']} declined this order, so PayPal released the hold. Nothing was charged.")
    return None


def decide(aid, approve):
    """Approver side, single use. Decline voids the hold at once. Returns the request, or None if not pending."""
    a = APPROVALS.get(aid)
    if not a or a['state'] != 'pending':
        return None
    if not approve:
        try:
            _void(a['auth_id'], a['rid'])
        except paypal.PayPalError:
            pass  # an unreleased hold is never captured and expires on its own
    a['state'] = 'approved' if approve else 'declined'
    return a


def confirm(s):
    st = state(s)
    if st == APPROVAL:
        return Reply(f"Still waiting for {APPROVALS.get(s['co']['approval'], {}).get('name', 'your trusted contact')} "
                     'to approve. Say cancel to release the hold.')
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
    if state(s) in HOLDING and s['co'].get('kind') != 'refund':
        try:
            _void(s['co']['auth_id'], s['co']['rid'])
        except paypal.PayPalError:
            pass  # an unreleased hold is never captured and expires on its own
        s['co'] = {'state': VOIDED}
    elif state(s) in HOLDING:
        s['co'] = {'state': IDLE}


def cancel(s):
    if state(s) not in HOLDING:
        return Reply('Nothing is on hold, so there is nothing to cancel.')
    if s['co'].get('kind') == 'refund':
        s['co'] = {'state': IDLE}
        return Reply('Return cancelled. Nothing was refunded.')
    try:
        _void(s['co']['auth_id'], s['co']['rid'])
    except paypal.PayPalError as e:
        return Reply(f'PayPal could not release the hold just now ({e}). Nothing was charged. Say cancel to try again.')
    if s['co'].get('approval') in APPROVALS:
        APPROVALS[s['co']['approval']]['state'] = 'cancelled'
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
    if s['co'].get('kind') == 'refund':
        return _refund(s)
    delay = int(os.environ.get('SIGHTLINE_UNDO_SECONDS', '10'))
    s['co'] = {**s['co'], 'state': UNDO, 'due': time.time() + delay}
    if delay <= 0:
        return finalize(s)
    return Reply(f'PIN accepted. PayPal takes the payment in {delay} seconds. '
                 'To stop it, say undo, or press Escape, or use the Undo button.')


# ---- returns: a refund goes through the same Readback -> confirm -> PIN steps as a payment ----
def start_refund(s, o, i):
    line = o['lines'][i]
    amount = min(Decimal(line['unit']) * line['qty'] + Decimal(line['tax']), Decimal(o['total']) - db.refunded(o))
    say, rb = speech.refund_readback(o, line, amount)
    s['co'] = {'state': CONFIRM, 'kind': 'refund', 'rid': uuid.uuid4().hex, 'order_id': o['order_id'], 'line': i,
               'amount': f'{amount:.2f}', 'say': say, 'lines': rb, 'pay': f'Refunding {speech.usd(amount)} to your PayPal'}
    return Reply(say, rb)


def _refund(s):
    co = s['co']
    o = db.get(co['order_id'])
    line = o['lines'][co['line']]
    try:
        r = paypal.refund(o['capture_id'], Decimal(co['amount']), co['rid'] + '-refund', f"Return of {line['name']}")
    except paypal.PayPalError as e:
        return Reply(f'PayPal did not make the refund ({e}). Nothing changed. Type the PIN to try again, or say cancel.')
    r.setdefault('amount', {'value': co['amount']})  # shortcut: PayPal omits amount on some minimal replies
    line['refunded'] = r['amount']['value']
    db.set_lines(o['order_id'], o['lines'])
    s['co'] = {'state': IDLE}
    return Reply(speech.refunded(r))


def seconds_left(s):
    return max(0, round(s['co']['due'] - time.time())) if state(s) == UNDO else 0


def finalize(s):
    """Capture once the undo window has passed. Safe to call repeatedly: same request id, counted once."""
    st, co = state(s), s.get('co', {})
    if st == CAPTURED:
        return Reply(f"Already paid. Order number {co['order_id']}.")
    if st != UNDO:
        return Reply('No payment is waiting.')
    if seconds_left(s) > 0:
        return Reply(f'Paying in {speech.plural(seconds_left(s), "second")}. Say undo to stop it.')
    led = ledger(s)
    with _lock:
        if co['rid'] in led['undone']:  # undone from another tab or an older cookie
            s['co'] = {'state': VOIDED}
            return Reply('That payment was undone. Nothing was charged.')
        try:
            cap = paypal.capture(co['auth_id'], co['rid'] + '-capture')
        except paypal.PayPalError as e:
            s['co'] = {**co, 'state': PIN}
            return Reply(f'PayPal did not take the payment ({e}). Nothing was charged. '
                         'Type the PIN to try again, or say cancel.')
        lines = [{'pid': pid, 'name': name, 'qty': q, 'unit': unit, 'refunded': '0.00',
                  'tax': f"{(Decimal(unit) * q * TAX_RATE).quantize(Decimal('0.01'), ROUND_HALF_UP)}"}
                 for pid, name, q, unit in co.get('items', [])]
        db.record(s['sid'], co['order_id'], cap['id'], cap['amount']['value'], lines, co.get('days', 0))
    s['co'] = {'state': CAPTURED, 'order_id': co['order_id'], 'rid': co['rid']}
    s['cart'] = []
    s.pop('gift', None)
    s['spell'] = co['order_id']
    return Reply(speech.receipt(cap, co['order_id']))


def undo(s):
    st, co = state(s), s.get('co', {})
    if st == CAPTURED:
        return Reply('Too late to undo: PayPal has already taken the payment.')
    if st in HOLDING:
        return cancel(s)
    if st != UNDO:
        return Reply('There is nothing to undo.')
    led = ledger(s)
    with _lock:  # a capture still in flight for this hold wins; otherwise the hold is voided before any capture
        if db.get(co['order_id']):
            return finalize(s)
        try:
            _void(co['auth_id'], co['rid'])
        except paypal.PayPalError as e:
            return Reply(f'PayPal could not release the hold just now ({e}). Nothing was charged yet. Say undo again.')
        led['undone'].add(co['rid'])
    s['co'] = {'state': VOIDED}
    return Reply('Undone. Nothing was charged. PayPal released the hold. Your cart is unchanged.')
