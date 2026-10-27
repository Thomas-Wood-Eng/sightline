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
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import checkout, lane0, lane1, paypal, speech
from .speech import Reply

STATIC = Path(__file__).resolve().parent / 'static'
app = FastAPI(title='Sightline')
app.add_middleware(SessionMiddleware, secret_key=os.environ['SESSION_SECRET'], same_site='lax',
                   https_only=os.environ.get('HTTPS_ONLY') == '1')
app.mount('/static', StaticFiles(directory=STATIC), name='static')


def out(s, r: Reply):
    s['last'] = {'say': r.say, 'lines': r.lines}
    return {'say': r.say, 'lines': r.lines, 'state': checkout.state(s), 'focus': r.focus, 'action': r.action}


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


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
            'spent_today': f"{led['spent']:.2f}", 'output_mode': s.get('mode', 'screen_reader'),
            'state': checkout.state(s),
            'summary': speech.settings_summary(c, s.get('mode', 'screen_reader'), bool(checkout.vault_id(s)),
                                               bool(s.get('pin')), led['spent'])}


@app.get('/api/settings')
def get_settings(request: Request):
    return settings_view(request.session)


class Settings(BaseModel):
    output_mode: str | None = None
    per_order_cap: str | None = None
    daily_cap: str | None = None
    new_pin: str | None = None
    current_pin: str | None = None


@app.post('/api/settings')
def post_settings(body: Settings, request: Request):
    s = request.session
    if body.output_mode is not None:
        if body.output_mode not in ('screen_reader', 'voice'):
            raise HTTPException(422, 'Output mode must be screen_reader or voice.')
        s['mode'] = body.output_mode
    if body.per_order_cap or body.daily_cap or body.new_pin:
        # caps and PIN change only here, and only with the current PIN (or a fresh PayPal login when unset)
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
            if not checkout.valid_pin(body.new_pin.strip()):
                raise HTTPException(422, 'The PIN must be exactly 4 digits.')
            checkout.set_pin(s, body.new_pin.strip())
        s['caps'] = caps
    return settings_view(s)


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
