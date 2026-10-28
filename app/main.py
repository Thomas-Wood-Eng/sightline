"""Sightline web app. Run: uvicorn app.main:app --port 8000"""
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / '.env').read_text().splitlines() if (ROOT / '.env').exists() else []:
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI, HTTPException, Request
from html import escape

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from itsdangerous import BadSignature
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import re

from . import checkout, lane0, lane1, paypal, speech
from .sessions import ServerSessions
from .speech import Reply

STATIC = Path(__file__).resolve().parent / 'static'
app = FastAPI(title='Sightline')
app.add_middleware(ServerSessions, secret_key=os.environ['SESSION_SECRET'],
                   https_only=os.environ.get('HTTPS_ONLY') == '1')
app.mount('/static', StaticFiles(directory=STATIC), name='static')


def out(s, r: Reply):
    s.pop('last', None)  # older cookies kept it here
    checkout.ledger(s)['last'] = {'say': r.say, 'lines': r.lines}
    return {'say': r.say, 'lines': r.lines, 'state': checkout.state(s), 'focus': r.focus, 'action': r.action,
            'due_in': checkout.seconds_left(s), 'pay': s.get('co', {}).get('pay'), 'paypal': checkout.paypal_view(s)}


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


@app.get('/sw.js')
def service_worker():
    # served from the root so its scope covers the whole app
    return FileResponse(STATIC / 'sw.js', media_type='text/javascript')


class Turn(BaseModel):
    text: str = Field(max_length=500)


@app.post('/api/turn')
def turn(body: Turn, request: Request):
    s, text = request.session, body.text.strip()
    if not text:
        return out(s, Reply('I did not catch anything. Type a request, or press Talk.'))
    try:
        r = lane0.handle(text, s) or lane1.handle(text, s)
    except paypal.PayPalError as e:
        r = Reply(f'PayPal had a problem ({e}). Nothing was charged. Say repeat or try again.')
    return out(s, r)


@app.post('/api/finalize')
def finalize(request: Request):
    """The page calls this when the undo window ends; any later turn would finalize too."""
    return out(request.session, checkout.finalize(request.session))


class Pin(BaseModel):
    pin: str = Field(max_length=12)


@app.post('/api/pin')
def pin(body: Pin, request: Request):
    return out(request.session, checkout.pin(request.session, body.pin.strip()))


def _cap(v):
    try:
        d = Decimal(str(v)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, 'Caps must be amounts in US dollars.')
    if not Decimal(1) <= d <= Decimal(10000):
        raise HTTPException(422, 'Caps must be between 1 and 10000 US dollars.')
    return str(d)


def settings_view(s):
    c = checkout.caps(s)
    led = checkout.ledger(s)
    return {'onboarded': bool(s.get('pin')) or led['locked'], 'pin_set': bool(s.get('pin')), 'locked': led['locked'],
            'linked': bool(checkout.vault_id(s)), 'per_order_cap': f"{c['order']:.2f}", 'daily_cap': f"{c['daily']:.2f}",
            'spent_today': f"{checkout.spent_today(s):.2f}", 'output_mode': s.get('mode', 'screen_reader'),
            'state': checkout.state(s), 'due_in': checkout.seconds_left(s), 'pay': s.get('co', {}).get('pay'), 'prefs': lane0.prefs(s), 'contact': s.get('contact'),
            'paypal': checkout.paypal_view(s),
            'resume': 'Welcome back. ' + checkout.pending(s) if checkout.pending(s) else None,
            'summary': speech.settings_summary(c, s.get('mode', 'screen_reader'), bool(checkout.vault_id(s)),
                                               bool(s.get('pin')), checkout.spent_today(s), lane0.prefs(s), s.get('contact'))}


@app.get('/api/settings')
def get_settings(request: Request):
    return settings_view(request.session)


class Settings(BaseModel):
    output_mode: str | None = None
    per_order_cap: str | None = None
    daily_cap: str | None = None
    new_pin: str | None = None
    current_pin: str | None = None
    default_size: str | None = Field(None, max_length=20)
    avoid_allergens: str | None = Field(None, max_length=200)
    verbosity: str | None = None
    large_text: bool | None = None
    simple_mode: bool | None = None
    contact_name: str | None = Field(None, max_length=40)
    contact_email: str | None = Field(None, max_length=120)
    approval_threshold: str | None = None


def _contact(body):
    """Trusted contact from the form, validated; None when the name is empty (no contact)."""
    name = (body.contact_name or '').strip()
    if not name:
        return None
    email = (body.contact_email or '').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise HTTPException(422, 'The trusted contact needs a valid email address.')
    return {'name': name, 'email': email, 'threshold': _cap(body.approval_threshold or '')}


def _prefs(s, body):
    """Saved preferences: set only here (the Settings form), never by chat."""
    p = lane0.prefs(s)
    if body.verbosity is not None:
        if body.verbosity not in ('brief', 'normal', 'detailed'):
            raise HTTPException(422, 'Verbosity must be brief, normal or detailed.')
        p['verbosity'] = body.verbosity
    if body.default_size is not None:
        p['size'] = body.default_size.strip()
    if body.avoid_allergens is not None:
        words = [w.strip().lower() for w in re.split(r',|\band\b', body.avoid_allergens) if w.strip()]
        p['avoid'] = list(dict.fromkeys(lane1.canon(w)[:30] for w in words))[:8]
    if body.large_text is not None:
        p['large_text'] = body.large_text
    if body.simple_mode is not None:
        p['simple'] = body.simple_mode
    s['prefs'] = p


@app.post('/api/settings')
def post_settings(body: Settings, request: Request):
    s = request.session
    body.new_pin = (body.new_pin or '').strip() or None  # a stray space in New PIN is "keep", not a bad PIN
    if body.new_pin and not checkout.valid_pin(body.new_pin):  # checked first, so the error names the right field
        raise HTTPException(422, 'The new PIN must be exactly 4 digits. Leave it empty to keep your PIN.')
    before = settings_view(s)
    if body.output_mode is not None:
        if body.output_mode not in ('screen_reader', 'voice'):
            raise HTTPException(422, 'Output mode must be screen_reader or voice.')
        s['mode'] = body.output_mode
    _prefs(s, body)
    current = checkout.caps(s)  # the form sends the caps back unchanged; only a real change needs the PIN
    if body.per_order_cap and _cap(body.per_order_cap) == f"{current['order']:.2f}":
        body.per_order_cap = None
    if body.daily_cap and _cap(body.daily_cap) == f"{current['daily']:.2f}":
        body.daily_cap = None
    contact = _contact(body) if body.contact_name is not None else s.get('contact')
    if body.per_order_cap or body.daily_cap or body.new_pin or contact != s.get('contact'):
        # caps, PIN and the trusted contact change only here, and only with the current PIN (or a fresh PayPal login when unset)
        if s.get('pin'):
            result = checkout.verify_pin(s, (body.current_pin or '').strip())
            if result != 'ok':
                raise HTTPException(403, checkout.LOCKED if result == 'locked' else 'Current PIN is not right.')
        elif checkout.ledger(s)['locked']:
            raise HTTPException(403, checkout.LOCKED)
        caps = dict(s.get('caps') or checkout.DEFAULT_CAPS)
        if body.per_order_cap:
            caps['order'] = _cap(body.per_order_cap)
        if body.daily_cap:
            caps['daily'] = _cap(body.daily_cap)
        if body.new_pin:
            checkout.set_pin(s, body.new_pin)
        s['caps'] = caps
        s['contact'] = contact
    view = settings_view(s)
    view['saved'] = speech.saved(before, view, bool(body.new_pin))
    return view


class Onboarding(BaseModel):
    screen_reader: bool
    pin: str
    per_order_cap: str = checkout.DEFAULT_CAPS['order']
    daily_cap: str = checkout.DEFAULT_CAPS['daily']


@app.post('/api/onboarding')
def onboarding(body: Onboarding, request: Request):
    s = request.session
    if s.get('pin') or checkout.ledger(s)['locked']:
        raise HTTPException(409, 'Setup is already done. Use Settings to change things.')
    if not checkout.valid_pin(body.pin.strip()):
        raise HTTPException(422, 'The PIN must be exactly 4 digits.')
    s['caps'] = {'order': _cap(body.per_order_cap), 'daily': _cap(body.daily_cap)}
    s['mode'] = 'screen_reader' if body.screen_reader else 'voice'
    checkout.set_pin(s, body.pin.strip())
    return settings_view(s)


# ---- trusted-contact approval page: signed, single-use, no login (the link is the secret) ----
def _approval(token):
    try:
        return checkout.signer().loads(token)
    except BadSignature:
        return None


def _page(title, body):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} - Sightline</title>
<link rel="stylesheet" href="/static/style.css"></head><body><main><h1>{escape(title)}</h1>{body}</main></body></html>""")


@app.get('/approve/{token}')
def approve_page(token: str):
    aid = _approval(token)
    a = checkout.APPROVALS.get(aid)
    if not a:
        return _page('Approval link not valid', '<p>This approval link is not valid, or the app was restarted.</p>')
    if a['state'] != 'pending':
        return _page('Already answered', f"<p>This request was already {escape(a['state'])}. Nothing more to do.</p>")
    items = ''.join(f'<li>{escape(l)}</li>' for l in a['lines'])
    buttons = ''.join(f'<form method="post" action="/approve/{escape(token)}/{d}"><button type="submit">{label}</button></form>'
                      for d, label in (('approve', 'Approve this order'), ('decline', 'Decline this order')))
    return _page(f"{a['name']}, please approve or decline this order",
                 '<p>Someone who listed you as their trusted contact wants to buy this with Sightline. PayPal is holding '
                 'the payment. Nothing is charged unless you approve and they then confirm with their own PIN.</p>'
                 f'<h2>The Readback, from PayPal</h2><ul>{items}</ul>{buttons}')


@app.post('/approve/{token}/{decision}')
def approve_decide(token: str, decision: str):
    if decision not in ('approve', 'decline'):
        raise HTTPException(404)
    a = checkout.decide(_approval(token), decision == 'approve')
    if not a:
        return _page('Already answered', '<p>This link was already used, or is not valid. Nothing changed.</p>')
    if decision == 'approve':
        return _page('Approved', '<p>Thank you. They can now finish the order with their PIN. Nothing is charged until they do.</p>')
    return _page('Declined', '<p>Declined. PayPal released the hold, so nothing was charged.</p>')


@app.get('/link/start')
def link_start(request: Request):
    base = str(request.base_url).rstrip('/')
    try:
        token, approve = paypal.link_start(base + '/link/return', base + '/link/cancel')
    except (paypal.PayPalError, KeyError):
        return RedirectResponse('/?link=error', 303)
    request.session['setup_token'] = token
    return RedirectResponse(approve, 303)


@app.get('/link/return')
def link_return(request: Request):
    s = request.session
    if not s.get('setup_token'):
        return RedirectResponse('/?link=error', 303)
    try:
        s['vault_id'], s['customer_id'] = paypal.link_return(s.pop('setup_token'))
    except paypal.PayPalError:
        return RedirectResponse('/?link=error', 303)
    if checkout.ledger(s)['locked']:
        checkout.unlock(s)  # a fresh PayPal login is the way out of a PIN lockout
    return RedirectResponse('/?link=done', 303)


@app.get('/link/cancel')
def link_cancel():
    return RedirectResponse('/?link=cancelled', 303)
