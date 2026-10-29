"""Checkout state machine: idle -> readback_pending -> awaiting_confirm -> awaiting_pin -> captured | voided.

Deterministic and LLM-free: confirm, cancel and the PIN only ever reach this file.
Caps are checked here before any hold. One PayPal-Request-Id per checkout attempt makes repeats replay, not re-charge.
"""
import hashlib, hmac, os, re, secrets, threading, time, uuid
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
LOCK_MINUTES = 15
LOCKED = (f'Your PIN is locked for {LOCK_MINUTES} minutes after three wrong tries. Nothing was charged. Wait '
          f'{LOCK_MINUTES} minutes, then try again; your trusted contact cannot unlock it. If you forgot your PIN: say link '
          'PayPal, or use the "Link PayPal again" link in the PayPal section of this page. Log in to PayPal; you then '
          'come back here, and the Setup form asks you to choose a new PIN.')

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


# ---- gift-card / pressure scam guard (flag set by Lane 0's fixed rules, never by an LLM) ----
SCAM_HOURS = 24  # shortcut: a flag lapses after a day so one false alarm can't block a shopper with no contact forever


def flag_scam(s, said, pressure):
    """Keep the first pressure words (the clearest reason for the contact); a later plain gift-card mention doesn't replace them."""
    old = scam_flag(s)
    if not old or (pressure and not old.get('pressure')):
        s['scam'] = {'said': said.strip()[:200], 'at': time.time(), 'pressure': pressure}


def scam_flag(s):
    f = s.get('scam')
    return f if f and time.time() - f['at'] < SCAM_HOURS * 3600 else None


def scam_hold(s):
    """The shopper's choice in Settings (on by default): a suspected scam waits for the trusted contact."""
    c = s.get('contact')
    return bool(c) and c.get('scam_hold', True)


def scam_reason(s, lines, quote=True):
    """Why Sightline suspects a scam, or None. The shopper's own words only with quote (the scam hold is their consent)."""
    f = scam_flag(s)
    if f and quote:
        return f'"{f["said"]}"'
    if any(p.get('gift_card') for p, _, _ in lines):
        return 'the order contains a gift card'
    return 'they had a scam warning from Sightline earlier' if f else None


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
    """'ok' | 'wrong' | 'locked' | 'format'. Wrong 4-digit tries count toward the lockout wherever the PIN is asked
    for; a blank or mistyped entry (not 4 digits) never does."""
    led, p = ledger(s), s.get('pin')
    if locked(s) or not p:
        return 'locked' if locked(s) else 'wrong'
    if not valid_pin(pin):
        return 'format'
    if hmac.compare_digest(_hash(pin, p['salt']), p['hash']):
        led['tries'] = 0
        return 'ok'
    led['tries'] += 1
    if led['tries'] >= MAX_TRIES:
        led['locked'] = time.time()  # when it locked; it opens again after LOCK_MINUTES
        _void_quietly(s)
        return 'locked'
    return 'wrong'


def locked(s):
    """Locked after three wrong tries, until LOCK_MINUTES have passed (then the tries start again)."""
    led = ledger(s)
    if led['locked'] and time.time() - led['locked'] >= LOCK_MINUTES * 60:
        led.update(tries=0, locked=False)
    return bool(led['locked'])


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
        return Reply('No new hold was placed. ' + pending(s))  # a repeated "check out" never re-reads it all
    if not s.get('cart'):
        return Reply('Your cart is empty. Search for something and add it first.')
    if locked(s):
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
    contact, hold = s.get('contact'), scam_hold(s)
    why = scam_reason(s, lines, quote=hold)
    if why and not contact:
        return Reply(speech.scam_no_contact())

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
    if contact and ((why and hold) or total > Decimal(contact['threshold'])):  # hold off: the warning, then the usual steps
        aid = secrets.token_urlsafe(16)
        APPROVALS[aid] = {'state': 'pending', 'name': contact['name'], 'lines': rb[:-1], 'auth_id': auth['id'], 'rid': rid,
                          'why': why}
        link = '/approve/' + signer().dumps(aid)
        rb = (rb[:-1] + speech.approval_sent(contact['name'], contact['threshold'], total, why if hold else None)
              + [f'Approval link: {link}'])
        s['co'].update(state=APPROVAL, approval=aid, lines=rb, link=link)
    return Reply(say, rb)


def approval_news(s):
    """Shopper side: has the trusted contact decided? Returns a Reply when something changed."""
    a = APPROVALS.get(s['co'].get('approval'))
    if a is None:
        return Reply('The approval request was lost when the app restarted. Say cancel to release the hold, '
                     'then check out again.')
    if a['state'] in ('approved', 'declined'):
        s.pop('scam', None)  # the contact has looked at it: the scam flag has done its job
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
    paying = s['co'].get('pay') or 'Paying'
    return Reply(f'PIN accepted. {paying} after a {delay}-second undo window. '
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


def pending(s):
    """What is pending, in plain words, from server data (also said on a page reload). None when nothing is."""
    st, co = state(s), s.get('co', {})
    if st not in HOLDING and st != UNDO:
        return None
    m = re.search(r'\d[\d,]*\.\d\d US dollars', co.get('pay') or '')  # 'pay' holds PayPal's own amount
    amount = m.group() if m else 'your order'
    if co.get('kind') == 'refund':
        o = db.get(co['order_id'])
        what = o['lines'][co['line']]['name'] if o else 'your return'
        step = 'type your PIN in the PIN box' if st == PIN else 'say confirm to continue'
        return (f'A refund of {amount} for {what} is waiting. To get it, {step}. '
                'Say repeat to hear the Readback, or cancel to keep the item.')
    names = [i[1] for i in co.get('items', [])]
    what = (names[0] + (f", and {speech.plural(len(names) - 1, 'more item')}" if len(names) > 1 else '')) if names else 'your order'
    if st == UNDO:
        left = seconds_left(s)
        when = f'in {speech.plural(left, "second")}' if left else 'now'
        return (f'Your PIN was accepted. Sightline asks PayPal to take the payment of {amount} for {what} {when}.'
                + (' To stop it, say undo, press Escape, or use the Undo button.' if left else ''))
    if st == APPROVAL:
        who = APPROVALS.get(co.get('approval'), {}).get('name', 'your trusted contact')
        return (f'A payment of {amount} for {what} is on hold, waiting for {who} to approve. Say approval link to get '
                f'the link for {who} again, repeat to hear the Readback, or cancel to release it.')
    if st == PIN:
        return (f'A payment of {amount} is on hold for {what}, waiting for your PIN. Type it in the PIN box, '
                'say repeat to hear the Readback, or say cancel to release it.')
    return (f'A payment of {amount} is on hold for {what}. '
            'Say repeat to hear the Readback, confirm to continue, or cancel to release it.')


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


# ---- the page's PayPal panel: linked status and where the current or last order stands at PayPal (server data) ----
def _paypal_amount(pay):
    m = re.search(r'\d[\d,]*\.\d\d US dollars', pay or '')  # 'pay' holds PayPal's own amount
    return m.group() if m else None


def paypal_view(s):
    co, st = s.get('co', {}), state(s)
    if co.get('order_id') and co.get('pay'):  # a hold or refund in progress; remembered after it ends
        s['pp'] = {'id': co['order_id'], 'kind': co.get('kind', 'payment'), 'line': co.get('line'),
                   'amount': _paypal_amount(co['pay']), 'contact': bool(co.get('approval'))}
    view = {'linked': bool(vault_id(s)), 'account': 'sandbox buyer account' if vault_id(s) else None, 'order': None}
    pp = s.get('pp')
    if not pp:
        return view
    o, amount, live = db.get(pp['id']), pp['amount'], co.get('order_id') == pp['id']
    if pp['kind'] == 'refund':
        steps = ['Captured by PayPal', 'You confirm with your Sightline PIN', 'Refunded by PayPal']
        line = o['lines'][pp['line']] if o else None
        if live and st in HOLDING:
            at, status = 1, f'A refund of {amount} is waiting for your confirm and PIN.'
        elif line and line['refunded'] != '0.00':
            amount = speech.usd(line['refunded'])
            at, status = 3, f'PayPal refunded {amount} to your PayPal.'
        else:
            steps, at, status = ['Captured by PayPal', 'Return cancelled'], 2, 'Return cancelled. Nothing was refunded.'
    else:
        steps = ['PayPal linked', 'On hold by PayPal'] + (['Trusted contact approves'] if pp['contact'] else []) + \
                ['You confirm with your Sightline PIN', 'Undo window', 'Captured by PayPal']
        if o:
            amount = speech.usd(o['total'])
            at, status = len(steps), f'PayPal captured {amount}.'
        elif live and st == APPROVAL:
            at, status = 2, f'PayPal is holding {amount}, waiting for your trusted contact to approve.'
        elif live and st in (CONFIRM, PIN):
            at = steps.index('You confirm with your Sightline PIN')
            status = f'PayPal is holding {amount}. Nothing is charged until you confirm and type your PIN.'
        elif live and st == UNDO:
            at, status = steps.index('Undo window'), f'PIN accepted. PayPal captures {amount} when the undo window ends.'
        else:  # voided, cancelled, declined or undone: the hold was released
            steps, at, status = ['PayPal linked', 'On hold by PayPal', 'Released by PayPal'], 2, \
                'PayPal released the hold. Nothing was charged.'
    view['order'] = {'id': pp['id'], 'kind': pp['kind'], 'amount': amount, 'status': status,
                     'ended': steps[-1] in ('Released by PayPal', 'Return cancelled'),
                     'steps': [{'label': l, 'state': 'done' if i < at else 'current' if i == at else 'next'}
                               for i, l in enumerate(steps)]}
    return view
