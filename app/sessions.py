"""Server-side sessions. The signed cookie carries only a random id; the state lives in SQLite (db.py).

Requests for one session run one at a time, so a slow PayPal capture can't overwrite a settings change made meanwhile.
`scope['session']` stays a plain dict, so endpoints use `request.session` as before.
"""
import asyncio, json, secrets
from collections import defaultdict

from itsdangerous import BadSignature, TimestampSigner
from starlette.requests import HTTPConnection

from . import db

COOKIE, MAX_AGE = 'session', 14 * 24 * 3600


class ServerSessions:
    def __init__(self, app, secret_key, https_only=False):
        self.app, self.signer = app, TimestampSigner(secret_key)
        self.flags = f'; path=/; Max-Age={MAX_AGE}; httponly; samesite=lax' + ('; secure' if https_only else '')
        self.locks = defaultdict(asyncio.Lock)  # shortcut: one small lock per session id, never freed; fine for a demo

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].startswith('/static/'):
            return await self.app(scope, receive, send)
        try:
            key = self.signer.unsign(HTTPConnection(scope).cookies[COOKIE], max_age=MAX_AGE).decode()
        except (KeyError, BadSignature):
            key = secrets.token_urlsafe(24)  # new session; only its own requests can know this id
        async with self.locks[key]:
            scope['session'] = db.load_session(key)
            before = json.dumps(scope['session'], sort_keys=True)

            async def send_saving(message):
                if message['type'] == 'http.response.start' and scope['session']:
                    after = json.dumps(scope['session'], sort_keys=True)
                    if after != before:
                        db.save_session(key, after)
                    cookie = f'{COOKIE}={self.signer.sign(key).decode()}{self.flags}'
                    message['headers'] = [*message.get('headers', []), (b'set-cookie', cookie.encode())]
                await send(message)

            await self.app(scope, receive, send_saving)
