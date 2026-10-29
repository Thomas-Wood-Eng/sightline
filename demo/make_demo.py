"""Render the pre-testing demo video from the REAL app:  python demo/make_demo.py  ->  demo/out/sightline_demo.mp4 + .srt

1. starts the app (with the pre-approved sandbox wallet, so checkout hits the real PayPal sandbox),
2. drives it in Chromium with Playwright and records the screen,
3. voices narrator, shopper and Sightline with Gemini TTS (free tier; cached in demo/out/tts/),
4. cuts out the seconds spent generating speech, lays each clip on its segment, burns captions with ffmpeg.
Shopper input is typed by the script (narrated as speech); everything the app says and does is real.
"""
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'demo' / 'out'
TTS = OUT / 'tts'
PORT = 8765
VOICES = {'narrator': 'Charon', 'you': 'Puck', 'sightline': 'Kore'}
sys.path.insert(0, str(ROOT))

INTRO = [
    ('title', 'Sightline', 'Shop by voice. Hear every dollar before it moves.',
     'This is Sightline: a voice and keyboard first shopping assistant for blind and low-vision people, built on PayPal. '
     'This is an early prototype, recorded before testing with blind users.'),
    ('narrate', 'Blind shoppers can often find a product, then lose it at checkout to pop-ups, captchas and unlabelled buttons. '
                'Sightline turns the whole purchase into a conversation.'),
    ('setup', 'Setup happens once: a PIN, spending limits, and an optional trusted contact, changed only in settings, never by voice. '
              "PayPal was linked beforehand on PayPal's own login page. Sightline's replies play faster, the way most "
              'screen-reader users listen.'),
]
ALLERGY = [
    ('narrate', 'Allergies are a hard filter in code, not a guess by the AI.'),
    ('say', 'I need a snack for my kid. She has a nut allergy.'),
]
HOODIE = [
    ('say', 'Find me a hoodie.'),
    ('say', 'Tell me about the first one.'),
    ('say', 'What do people say about it?'),
    ('say', 'Add it.'),
    ('say', 'Medium.'),
    ('say', "It's a gift."),
    ('say', 'Happy birthday, Sam!'),
]
PAY = [
    ('say', 'Check out.'),
    ('narrate', "Every amount you just heard came from PayPal's own order, not from the AI. "
                'The money stays on hold until the shopper confirms and types their PIN.'),
    ('say', 'Confirm.'),
    ('pin', '1234'),
    ('captured',),
]
SCAM = [
    ('narrate', 'Sightline also calls out sales tricks, like a protection plan the seller pre-ticks.'),
    ('say', 'Find headphones.'),
    ('say', 'Add the first one.'),
    ('say', 'Check out.'),
    ('say', 'Cancel.'),
]
APPROVAL = [   # "Undo." must follow the PIN directly: the 10-second window is real time
    ('narrate', 'Above an amount the shopper chose, a trusted contact has to approve the order first.'),
    ('say', 'Find a rain jacket.'),
    ('say', 'Add it.'),
    ('say', 'Check out.'),
    ('approve', 'Alex gets a link, sees the same Readback, and approves.'),
    ('say', 'Confirm.'),
    ('pin', '1234'),
    ('say', 'Undo.'),
    ('narrate', 'For ten seconds after the PIN, the shopper can still change their mind. Nothing was charged.'),
]
REFUND = [
    ('say', 'Return the hoodie.'),
    ('say', 'Confirm.'),
    ('pin', '1234'),
]
OUTRO = [
    ('title', 'The AI suggests. It never holds the keys.', 'Next: testing with blind and low-vision shoppers.',
     'The agent does the clicking. The person makes every decision. Next, testing with blind and low-vision shoppers.'),
]

# Feature showcase ("ad", ~90 s): headline beats over the real app; only the key sentence of each reply is voiced.
AD = [
    ('title', 'Sightline', 'Shopping by voice, for blind and low-vision people.',
     'Meet Sightline. Shopping by voice, built for blind and low-vision people, on PayPal.'),
    ('setup', 'Set up once.'),
    ('card', 'Link PayPal once, on PayPal’s own page.', 'paypal_link.png', [],
     'Link PayPal once, on PayPal’s own page. After that, shopping is by voice.'),
    ('beat', 'Ask in your own words.'),
    ('say', 'Find me a hoodie.', ['results']),
    ('beat', 'Hear what the listing says, and what the photo suggests.'),
    ('say', 'Tell me about the first one.', ['Heavyweight pullover hoodie.']),
    ('beat', 'Hear every dollar before it moves.'),
    ('say', 'Add the first one.', ['Which size']),
    ('say', 'Medium.', ['Added']),
    ('say', 'Check out.', ['Total:']),
    ('beat', 'Nothing moves until you confirm.'),
    ('say', 'Confirm.', ['PIN']),
    ('pin', '1234', ['10 seconds']),
    ('say', 'Undo.', ['Undone', 'Nothing was charged']),
    ('beat', 'Sales tricks get called out.'),
    ('hidden', 'Remove the hoodie.'),
    ('say', 'Find headphones.', ['results']),
    ('say', 'Add the first one.', ['Added']),
    ('say', 'Check out.', ['Heads up', 'did not add']),
    ('hidden', 'Cancel.'),
    ('hidden', 'Remove the headphones.'),
    ('beat', 'Bigger orders? A trusted contact approves.'),
    ('say', 'Find a rain jacket.', ['results']),
    ('say', 'Add it.', ['Added']),
    ('say', 'Check out.', ['Sent to Alex']),
    ('approve', 'Alex approves from their phone.'),
    ('card', 'How Sightline uses PayPal', None, [
        'Link once: PayPal Vault saves the PayPal account.',
        'Check out: PayPal holds the money (Orders, authorize).',
        'The Readback uses PayPal’s own numbers.',
        'Confirm + PIN: PayPal captures the payment.',
        'Undo or cancel: PayPal releases the hold.'],
     'PayPal saves the account once, holds every order, and captures only after the PIN. Undo, and PayPal releases it.'),
    ('title', 'The AI suggests. It never holds the keys.', 'Sightline: PayPal AI Hackathon 2026',
     'The AI suggests. It never holds the keys. Sightline.'),
]
SCRIPTS = {'ad': AD, 'full': INTRO + ALLERGY + HOODIE + PAY + SCAM + [('say', 'Remove the headphones.')] + APPROVAL + REFUND + OUTRO,
           # Devpost cut, must stay under 3 minutes: the problem, one purchase, the trusted contact and undo
           'short': [
               ('title', 'Sightline', 'Shop by voice. Hear every dollar before it moves.',
                'Blind shoppers often lose a purchase at checkout. Sightline is voice-first shopping, built on PayPal.'),
               ('setup', "Setup happens once: a PIN, spending limits, and a trusted contact. Replies play at "
                         'screen-reader speed.'),
               ('card', 'Link PayPal once, on PayPal’s own page.', 'paypal_link.png', [],
     'Link PayPal once, on PayPal’s own page. After that, shopping is by voice.'),
               ('say', 'Find me a hoodie.', ['results']), ('say', 'Add the first one.', ['Which size']),
               ('say', 'Medium.', ['Added']),
               ('say', 'Check out.'),   # the one Readback voiced in full
               ('say', 'Confirm.', ['PIN']), ('pin', '1234', ['10 seconds']), ('captured',),
               ('narrate', 'Above a set amount, a trusted contact approves first.'),
               ('say', 'Find a rain jacket.', ['results']), ('say', 'Add it.', ['Added']),
               ('say', 'Check out.', ['Total:', 'Sent to Alex']),
               APPROVAL[4],
               ('say', 'Confirm.', ['PIN']), ('pin', '1234', ['10 seconds']),
               ('say', 'Undo.', ['Undone', 'Nothing was charged']),
               ('card', 'How Sightline uses PayPal', None, [
        'Link once: PayPal Vault saves the PayPal account.',
        'Check out: PayPal holds the money (Orders, authorize).',
        'The Readback uses PayPal’s own numbers.',
        'Confirm + PIN: PayPal captures the payment.',
        'Undo or cancel: PayPal releases the hold.'],
     'PayPal saves the account once, holds every order, and captures only after the PIN. Undo, and PayPal releases it.'),
               ('title', 'The AI suggests. It never holds the keys.', 'github.com/Thomas-Wood-Eng/sightline',
                'And for ten seconds, they can still undo. The AI suggests. It never holds the keys.'),
           ]}
# quick check of camera, callouts, screen-off and the caption bar
SCRIPTS['test'] = [
    ('setup', 'Set up once.'),
    ('dark', True, 'Screen off: this is what the shopper hears.'),
    ('say', 'Find me a hoodie.', ['results']),
    ('dark', False),
    ('say', 'Add the first one.', ['Which size']), ('say', 'Medium.', ['Added']),
    ('say', 'Check out.', ['Total:'], [('cam', '.reply.readback'), ('callout', '#log .reply.readback .line.total', 'Total from PayPal')]),
    ('cam', '#paypal', 1.6), ('callout', '#pp-steps', 'PayPal is holding the money'),
    ('narrate', 'PayPal holds the money until the shopper confirms.'),
    ('say', 'Confirm.', ['PIN'], [('cam', '#pin-form')]),
    ('pin', '1234', ['10 seconds'], [('cam', '#undo-box')]),
    ('captured',),
]
# ---- v5 storyboards: chapters, camera on what matters, short spoken replies ----
LAST = '#log .reply'   # the newest reply bubble (cam/callout take the last match)
PAYPAL_FLOW = ('card', 'How Sightline uses PayPal', None, [
    'Link once: PayPal Vault saves the account.',
    'Check out: PayPal holds the money (Orders v2, authorize).',
    'The Readback reads PayPal’s own numbers.',
    'After the PIN: Sightline asks PayPal to capture.',
    'Undo or cancel: PayPal voids the hold.'],
    'Under the hood: PayPal saves the account once and holds every order. '
    'Sightline asks PayPal to capture only after the PIN. Undo, and PayPal releases the hold.')
EXTENSION = ('card', 'The same check on other checkouts', 'extension_readback.png', [],
             'A browser extension prototype brings the same check to checkout pages: the exact amount and payee, '
             'read aloud, then a PIN.')
OPEN = [
    ('title', 'Sightline', 'Shop by voice or keyboard. Hear every dollar before it moves.',
     'Checkout is where blind shoppers get stuck. Sightline makes it a conversation.'),
    ('setup', 'Set up once: a PIN, spending limits, and an optional trusted contact, Alex, for orders over 75 dollars.'),
    ('card', 'Link PayPal once, on PayPal’s own page.', 'paypal_link.png', ['PayPal sandbox consent page'], ''),
]
ASK = [
    ('beat', '1. Ask in your own words (typed in this video; push-to-talk works too)'),
    ('dark', True, 'Screen off. This is what the shopper hears.'),
    ('say', 'Find me a hoodie.'),
    ('dark', False),
]
BUY = [
    ('say', 'Add the first one.', ['Which size']),
    ('say', 'Medium.', ['Added']),
    ('beat', '2. Hear the real total, from PayPal'),
    ('say', 'Check out.', ['Item 1', 'Unit price', 'Shipping', 'Tax', 'Total:', 'Delivery', 'Seller', 'Pay in 4'],
     [('cam', '.reply.readback'), ('callout', '#log .reply.readback .line.total', 'Every number from PayPal’s order')]),
    ('cam', '#paypal', 1.4), ('callout', '#pp-order', 'PayPal is holding the money. Nothing charged yet.'),
    ('still', 2.2, 'PayPal is holding the money. Nothing is charged yet.'),
    ('beat', '3. Confirm, then type a PIN'),
    ('say', 'Confirm.', ['PIN'], [('cam', '#pin-form')]),
]
SAFETY = [
    ('beat', 'Scam warnings'),
    ('say', 'A caller says I have to buy gift cards today.', ['common scam', 'only if'], [('cam', LAST)]),
    ('say', 'Find me a gift card.', ['results']),
    ('say', 'Add number 1.', ['Added']),
    ('say', 'Check out.', ['flagged', 'Approval link ready'],
     [('cam', '#paypal', 1.4), ('callout', '#pp-order', 'Under $75, but flagged: waiting for Alex')]),
    ('approve', 'Alex sees why it was flagged, and declines.', 'decline'),
    ('say', 'Confirm.', ['declined'], [('cam', '#paypal', 1.4), ('callout', '#pp-order', 'PayPal released the hold')]),
    ('note_order', 'Gift card: declined by Alex'),
]
SCRIPTS['short'] = OPEN + ASK + BUY + [
    ('pin', '1234', ['Paying'], [('cam', '#undo-box'), ('callout', '#undo-btn', 'Focus on Undo for 10 seconds')]),
    ('captured', ['Paid'], ('cam', '#paypal', 1.4), ('callout', '#pp-order', 'Charged by PayPal')),
    ('note_order', 'Hoodie: paid'),
] + SAFETY + [
    ('beat', 'After delivery: is this my package?'),
    ('say', 'Check my hoodie package.', ['-'], [('cam', '#package-photo', 1.3), ('callout', '#package-photo', 'Package photo button')]),
    ('photo', 'delivery_photo.jpg', ['Photo suggests'], ('cam', LAST)),
    ('proof', 'Both orders, straight from PayPal’s sandbox: one paid, one released.'),
    ('card', 'The same check on other checkouts: a browser extension prototype', 'extension_readback.png',
     ['Reads the page’s own total and payee, then asks for the PIN. Tested on look-alike pages only.'], ''),
    ('title', 'The AI suggests. The shopper decides.', 'github.com/Thomas-Wood-Eng/sightline  ·  Photos: Wikimedia Commons',
     'The AI suggests. The shopper decides.'),
]
SCRIPTS['ad'] = OPEN + ASK + [
    ('beat', 'Compare without the clutter'),
    ('say', 'Compare those two.', None, [('cam', LAST)]),
] + BUY + [
    ('pin', '1234', ['Paying'], [('cam', '#undo-box'), ('callout', '#undo-btn', 'Focus on Undo for 10 seconds')]),
    ('captured', ['Paid'], ('cam', '#paypal', 1.4), ('callout', '#pp-order', 'Charged by PayPal')),
    ('note_order', 'Hoodie: paid'),
] + SAFETY + [
    ('beat', 'Price drops, said once'),
    ('say', 'Tell me if the fleece-lined hoodie drops below 30 dollars.', None, [('cam', LAST)]),
    ('api', '/api/demo/price', {'id': 'hoodie-01', 'price': '29.99'}),
    ('beat', 'Something wrong? Help by voice'),
    ('say', 'The hoodie came damaged.', None, [('cam', LAST)]),
    ('hidden', 'No.'),
    ('beat', 'Is this my package?'),
    ('say', 'Check my hoodie package.', ['-'], [('cam', '#package-photo', 1.3), ('callout', '#package-photo', 'Package photo button')]),
    ('photo', 'delivery_photo.jpg', ['Photo suggests'], ('cam', LAST)),
    PAYPAL_FLOW, EXTENSION,
    ('title', 'The AI suggests. It never holds the keys.', 'github.com/Thomas-Wood-Eng/sightline',
     'The AI suggests. The shopper decides. PayPal holds the money until they do.'),
]
SCRIPT = SCRIPTS['full']


# ---------- speech ----------
# Narrator and shopper: Gemini TTS (most natural; free tier = 10 clips/day per model, so rotate models and cache).
# Sightline: local Kokoro (unlimited; its even delivery suits a screen-reader-style assistant). If Gemini's daily
# quota is gone, Kokoro voices stand in so a render always finishes; the next run retries Gemini for those clips.
GEMINI_TTS = ['gemini-3.8-flash-tts', 'gemini-3.1-flash-tts-preview', 'gemini-3.8-flash-lite-tts', 'gemini-2.5-flash-preview-tts']
KOKORO_VOICES = {'sightline': 'af_heart', 'narrator': 'bm_george', 'you': 'am_puck'}
_spent = set()   # Gemini models whose daily quota ran out this run
_kokoro = None


def _gemini(text, who, path, style=True):
    from google.genai import types
    from app.llm import client
    prompt = ({'narrator': 'Read like a calm, warm documentary narrator: ',
               'you': 'Say naturally, like a person casually talking to a voice assistant: '}[who] if style else '') + text
    config = types.GenerateContentConfig(response_modalities=['AUDIO'], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICES[who]))))
    for model in GEMINI_TTS:
        for attempt in (1, 2):  # second try only after a per-minute limit (3/min)
            if model in _spent:
                break
            try:
                r = client().models.generate_content(model=model, contents=prompt, config=config)
                blob = r.candidates[0].content.parts[0].inline_data
                if blob.data[:4] == b'RIFF':  # some models return a complete WAV file...
                    path.write_bytes(blob.data)
                else:  # ...others raw 16-bit PCM, e.g. "audio/L16;codec=pcm;rate=24000"
                    rate = int((re.search(r'rate=(\d+)', blob.mime_type or '') or [0, 24000])[1])
                    with wave.open(str(path), 'wb') as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(rate)
                        w.writeframes(blob.data)
                return True
            except Exception as e:
                print(f'  {model}: {str(e)[:70]}')
                if attempt == 2 or 'PerDay' in str(e) or 'NOT_FOUND' in str(e) or '404' in str(e):
                    _spent.add(model)
                else:
                    time.sleep(25)
    return False


def _kokoro_tts(text, who, path):
    global _kokoro
    import soundfile as sf
    from kokoro_onnx import Kokoro
    if _kokoro is None:
        _kokoro = Kokoro(str(ROOT / 'demo/models/kokoro-v1.0.onnx'), str(ROOT / 'demo/models/voices-v1.0.bin'))
    audio, sr = _kokoro.create(text, voice=KOKORO_VOICES[who], speed=1.0, lang='en-us')
    sf.write(str(path), audio, sr)


# Orpheus (Groq, free key in .env as GROQ_API_KEY): the most expressive voices; tried first for every role.
ORPHEUS_VOICES = {'narrator': 'daniel', 'you': 'hannah', 'sightline': 'diana'}
_orpheus_off = False


def _fix_wav(raw):
    """Groq streams WAV with placeholder RIFF/data lengths; rewrite them from the real byte count."""
    i = raw.find(b'data')
    if raw[:4] != b'RIFF' or i < 0:
        return raw
    out = bytearray(raw)
    struct.pack_into('<I', out, 4, len(raw) - 8)
    struct.pack_into('<I', out, i + 4, len(raw) - (i + 8))
    return bytes(out)


def _orpheus(text, who, path):
    global _orpheus_off
    env = dict(l.split('=', 1) for l in (ROOT / '.env').read_text().splitlines() if '=' in l)
    key = os.environ.get('GROQ_API_KEY') or env.get('GROQ_API_KEY', '').strip()
    if _orpheus_off or not key:
        return False
    # short requests sound best and stay under per-request input limits: one sentence group per call, then join
    chunks, cur = [], ''
    for s in re.split(r'(?<=[.!?])\s+', text.strip()):
        if cur and len(cur) + len(s) > 180:
            chunks.append(cur)
            cur = s
        else:
            cur = f'{cur} {s}'.strip()
    chunks.append(cur)
    frames, params = [], None
    for c in chunks:
        req = urllib.request.Request('https://api.groq.com/openai/v1/audio/speech', method='POST', data=json.dumps(
            {'model': 'canopylabs/orpheus-v1-english', 'input': c, 'voice': ORPHEUS_VOICES[who], 'response_format': 'wav'}).encode(),
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        try:
            raw = _fix_wav(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            print(f'  orpheus HTTP {e.code}: {e.read().decode(errors="replace")[:160]}')
            if e.code in (400, 401, 403) or 'day' in str(e).lower():
                _orpheus_off = True   # bad key, terms not accepted, or daily limit: stop trying this run
            return False
        except OSError as e:
            print(f'  orpheus network: {e}')
            return False
        with wave.open(io.BytesIO(raw)) as w:
            params = params or w.getparams()
            frames.append(w.readframes(w.getnframes()))
    with wave.open(str(path), 'wb') as w:
        w.setparams(params)
        w.writeframes(b''.join(frames))
    return True


def spoken(text):
    """Money the way people say it: TTS engines read "$52.00" as "dollar fifty-two point zero zero". Speech only;
    captions keep the app's exact words."""
    money = lambda m: f"{int(m[1])} dollars" + ('' if m[2] == '00' else f" and {int(m[2])} cents")
    text = re.sub(r'\$(\d+)\.(\d\d)', money, text)
    return re.sub(r'(\d+)\.(\d\d) US dollars', money, text)


def forget(clip):
    """Drop a cached clip with its processed copies and its transcription check."""
    for f in clip.parent.glob(clip.stem + '.*'):
        if f.name == clip.name or f.name.startswith(clip.stem + '.p') or f.suffix == '.checked':
            f.unlink()


def said_right(path, text):
    """Transcribe a Gemini clip once (result cached next to it): False if it speaks words that aren't in the text,
    like the style instruction."""
    mark = path.with_suffix('.checked')
    if mark.exists():
        return mark.read_text() == 'ok'
    from google.genai import types
    from app.llm import client
    heard = client().models.generate_content(model='gemini-3.5-flash-lite', contents=[
        types.Part.from_bytes(data=path.read_bytes(), mime_type='audio/wav'), 'Transcribe exactly, word for word.']).text
    leak = any(w in heard.lower() and w not in text.lower() for w in ('narrator', 'read like', 'say naturally', 'voice assistant'))
    mark.write_text('bad' if leak else 'ok')
    if leak:
        print(f'  TTS said its instruction, redoing: {heard[:80]}')
    return not leak


def tts(text, who):
    """-> (cached wav path, seconds). Orpheus first, then Gemini (narrator/shopper), then local Kokoro."""
    text = spoken(text)
    TTS.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f'{who}|{text}'.encode()).hexdigest()[:16]
    orp, gem, kok = TTS / f'{key}.orpheus.wav', TTS / f'{key}.wav', TTS / f'{key}.kokoro.wav'
    local_only = os.environ.get('DEMO_TTS') == 'kokoro'  # test renders: no quota spent, hosted cache untouched
    path = None
    if not local_only:
        # Orpheus beats a cached Gemini clip, so adding GROQ_API_KEY later upgrades the voices on the next render
        if orp.exists() or _orpheus(text, who, orp):
            path = orp
        elif gem.exists():
            path = gem
        # Gemini's 10 clips/day per model only covers the narrator; the shopper stays on one engine (Kokoro)
        # so a role never switches voice halfway through when the quota runs out
        elif who == 'narrator' and len(_spent) < len(GEMINI_TTS) and _gemini(text, who, gem):
            path = gem
        # Gemini TTS sometimes reads its style instruction aloud: listen once, retry plain, else use Kokoro
        if path == gem and not said_right(gem, text):
            forget(gem)
            path = gem if (len(_spent) < len(GEMINI_TTS) and _gemini(text, who, gem, style=False)
                           and said_right(gem, text)) else None
            if path is None:
                forget(gem)
    if path is None:
        if not kok.exists():
            _kokoro_tts(text, who, kok)
        path = kok
    # Every clip: same loudness (engines differed by up to 7 dB), short fades so cuts never click, and Sightline a little
    # faster, the way screen-reader users listen. Cached per source clip and setting.
    speed = {'sightline': SIGHTLINE_SPEED, 'narrator': NARRATOR_SPEED}.get(who, 1.0)
    done = path.with_name(path.stem + f'.p{speed}.wav')
    if not done.exists():
        # Gemini pads clips with seconds of silence: trim both ends (the reversed pass trims the tail),
        # fade the new ends so cuts never click
        trim = 'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08'
        # and its slow narrator read leaves long mid-sentence pauses: shorten any pause to a quarter second
        pauses = 'silenceremove=stop_periods=-1:stop_duration=0.3:stop_threshold=-35dB:stop_silence=0.25'
        chain = ([f'atempo={speed}'] if speed != 1.0 else []) + [
            pauses, trim, 'afade=t=in:d=0.02', 'areverse', trim, 'afade=t=in:d=0.04', 'areverse', 'loudnorm=I=-16:TP=-1.5:LRA=11']
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path), '-af', ','.join(chain),
                        '-ar', '24000', '-ac', '1', str(done)], check=True)
    with wave.open(str(done)) as w:
        return done, w.getnframes() / w.getframerate()


SIGHTLINE_SPEED = 1.15   # screen-reader users go faster; 1.15 keeps it followable for first-time viewers
# every page and frame gets a speech engine that does nothing, so a render never makes a sound on this computer
SILENT = '''Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: {speaking: false, pending: false,
  paused: false, speak() {}, cancel() {}, pause() {}, resume() {}, getVoices: () => [], addEventListener() {}}});'''
NARRATOR_SPEED = 1.1
BASE = 1.5    # recording draws the app 1.5x (laid out 1280 wide)
APP_H = 940   # app area of the 1920x1080 frame; the rest is the caption bar


# ---------- recording ----------
def start_server():
    vault = json.loads((ROOT / 'spike_state.json').read_text())['vault_id']
    env = dict(os.environ, DEMO_VAULT_ID=vault, PYTHONIOENCODING='utf-8', SIGHTLINE_DEMO='1')  # demo price override on
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', str(PORT)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=1)
            return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError('server did not start')


def record():
    from app import paypal   # the proof step reads PayPal's own record of each order
    env = dict(l.split('=', 1) for l in (ROOT / '.env').read_text().splitlines() if '=' in l)
    os.environ.update({k: v.strip() for k, v in env.items() if k.startswith('PAYPAL_')})
    segments = []  # (start_s, end_s, wav or None, caption)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--mute-audio'])
        # The final frame adds a caption bar below the app, so a subtitle never covers what it talks about.
        ctx = browser.new_context(viewport={'width': 1920, 'height': APP_H}, record_video_dir=str(OUT / 'raw'),
                                  record_video_size={'width': 1920, 'height': APP_H})
        # the video is voiced separately; never let the page speak through the computer's speakers
        ctx.add_init_script(SILENT)
        page = ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0
        # recording only: lay the app out 1280 wide and let the camera draw it at 1.5x (everything reads 50% bigger
        # than a plain 1080p capture, and the browser re-renders it sharp); a taller conversation fits a whole Readback
        css = f'html {{ overflow: hidden; }} body {{ width: {1920 // BASE}px; }} .talk #log {{ height: 280px !important; }}'
        ctx.add_init_script(f'''if (window.top === window) addEventListener('DOMContentLoaded', () => {{
            const s = document.createElement('style'); s.textContent = {json.dumps(css)}; document.head.append(s); }});''')
        page.goto(f'http://127.0.0.1:{PORT}/')
        page.wait_for_timeout(800)

        def hold(wav, dur, caption):
            a = now()
            page.wait_for_timeout(int(dur * 1000) + 350)
            segments.append((a, now(), wav, caption))

        def overlay(title, sub):
            page.evaluate('''([t, s]) => { const d = document.createElement('div'); d.id = 'demo-title';
                d.style.cssText = 'position:fixed;inset:0;z-index:99;background:#0b1f3a;color:#fff;display:flex;flex-direction:column;'
                  + 'align-items:center;justify-content:center;font:600 54px system-ui;text-align:center;padding:40px';
                d.innerHTML = '<div></div><div style="font:400 28px system-ui;margin-top:24px;opacity:.85"></div>';
                d.children[0].textContent = t; d.children[1].textContent = s; document.documentElement.append(d); }''', [title, sub])

        def last_reply():
            return page.evaluate('''() => { const t = [...document.querySelectorAll('#log .turn')].pop();
                return [...t.querySelectorAll('p:not(.you)')].map(p => p.textContent).join('\\n'); }''')

        def wait_turn(n):
            page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=60000)
            page.evaluate('window.scrollTo(0, 0)')  # keep the conversation, product and banner in frame
            page.wait_for_timeout(250)

        zoomed = False

        def cam(sel=None, max_scale=1.6):
            """Camera move done by the browser itself (zoomed text stays sharp): scale the page around `sel`,
            or back to the full view with None. max_scale is relative to the full view."""
            nonlocal zoomed
            zoomed = sel is not None
            page.evaluate('''([sel, base, maxS]) => { const b = document.body, W = innerWidth, H = innerHeight;
                document.getElementById('demo-callout')?.remove();
                b.style.transition = 'none'; const prev = b.style.transform; b.style.transform = 'none';
                const el = sel && [...document.querySelectorAll(sel)].pop(); let t = `scale(${base})`;
                if (el) { el.scrollIntoView({block: 'nearest'}); scrollTo(0, 0); const r = el.getBoundingClientRect();
                  const s = Math.max(base, Math.min(base * maxS, 0.94 * W / r.width, 0.92 * H / r.height));
                  const clamp = (v, lo) => Math.min(0, Math.max(lo, v));
                  const tx = clamp(W / 2 - s * (r.left + r.width / 2), W - s * b.offsetWidth);
                  const ty = clamp(H / 2 - s * (r.top + r.height / 2), H - s * b.scrollHeight);
                  t = `translate(${tx}px, ${ty}px) scale(${s})`; }
                b.style.transform = prev; b.offsetWidth; b.style.transformOrigin = '0 0';
                b.style.transition = 'transform .7s cubic-bezier(.3,.1,.2,1)'; b.style.transform = t; }''', [sel, BASE, max_scale])
            page.wait_for_timeout(750)

        def callout(sel, text):
            """A ring around `sel` plus a short label, so the viewer knows where to look."""
            page.evaluate('''([sel, text]) => { document.getElementById('demo-callout')?.remove();
                const el = [...document.querySelectorAll(sel)].pop(); if (!el) return;
                el.scrollIntoView({block: 'nearest'}); scrollTo(0, 0);
                const r = el.getBoundingClientRect(), d = document.createElement('div'); d.id = 'demo-callout';
                d.style.cssText = `position:fixed;z-index:97;pointer-events:none;left:${r.left - 6}px;top:${r.top - 6}px;`
                  + `width:${r.width + 12}px;height:${r.height + 12}px;border:6px solid #ffb800;border-radius:16px;`
                  + 'box-shadow:0 0 0 9999px rgba(11,31,58,.3)';
                const l = document.createElement('div'); l.textContent = text;
                l.style.cssText = `position:absolute;left:-4px;${r.top > 100 ? 'bottom' : 'top'}:calc(100% + 8px);white-space:nowrap;`
                  + 'background:#ffb800;color:#0b1f3a;font:700 30px system-ui;padding:8px 18px;border-radius:12px';
                d.append(l); document.documentElement.append(d);
                const over = l.getBoundingClientRect().right - (innerWidth - 8);   // keep the label on screen
                if (over > 0) l.style.left = `${-4 - over}px`; }''', [sel, text])
            page.wait_for_timeout(200)

        def dark(on, label=''):
            """Screen off: what the shopper actually gets is the audio."""
            page.evaluate('''([on, label]) => { document.getElementById('demo-dark')?.remove(); if (!on) return;
                const d = document.createElement('div'); d.id = 'demo-dark';
                d.style.cssText = 'position:fixed;inset:0;z-index:96;pointer-events:none;background:#05070c;color:#c9d3e3;display:flex;'
                  + 'align-items:center;justify-content:center;font:500 38px system-ui';
                d.style.flexDirection = 'column'; d.style.gap = '36px';
                const bars = document.createElement('div'); bars.style.cssText = 'display:flex;gap:10px;align-items:center;height:120px';
                for (let k = 0; k < 9; k++) { const b = document.createElement('i');
                  b.style.cssText = `display:block;width:14px;border-radius:7px;background:#ffb800;height:30px;`
                    + `animation:demo-eq ${0.55 + (k % 4) * 0.13}s ease-in-out ${k * 0.07}s infinite alternate`; bars.append(b); }
                const st = document.createElement('style');
                st.textContent = '@keyframes demo-eq { from { height: 14px } to { height: 110px } }';
                const t = document.createElement('div'); t.textContent = label;
                d.append(st, bars, t); document.documentElement.append(d); }''', [on, label])
            page.wait_for_timeout(400)

        def do(action):  # ('cam', selector|None[, max_scale]) / ('callout', selector, label) / ('dark', on[, label])
            {'cam': cam, 'callout': callout, 'dark': dark}[action[0]](*action[1:])

        def key_sentences(reply, hints):
            """Voice only the sentences that carry the point (all of them without hints); the full reply stays on
            screen. Splits on the app's own lines first, so a numbered result ("1. Hoodie, $52.00") stays whole."""
            parts = []
            for line in reply.split('\n'):
                parts += [line] if re.match(r'\d+\. ', line) else re.split(r'(?<=[.!?])\s+', line)
            picked = [p for p in parts if any(h.lower() in p.lower() for h in hints or [''])]
            return ' '.join(picked or parts[:1])

        def submit(selector, text, voiced, hints=None, after=()):
            n = page.locator('#log .turn').count()
            wav, dur = (None, 1.2) if selector == '#pin' else tts(voiced, 'you')
            if zoomed and selector != '#pin':
                cam(None)   # back to the full view so the typing is visible
            a = now()
            page.click(selector)
            page.keyboard.type(text, delay=max(20, min(90, int(dur * 800 / max(len(text), 1)))))
            if selector == '#pin':
                page.wait_for_timeout(700)   # the masked dots stay on screen a moment
            page.keyboard.press('Enter')
            wait_turn(n)
            segments.append((a, min(now(), a + dur + 1.2), wav, f'You: {voiced}'))
            reply = last_reply()
            for action in after:   # point the camera at what the reply is about
                do(action)
            if hints == ['-']:     # on screen only, not voiced (e.g. an instruction heard a minute ago)
                hold(None, 1.2, '')
                return
            reply = key_sentences(reply, hints)
            wav, dur = tts(reply, 'sightline')  # generated while the screen is static; this gap is cut later
            hold(wav, dur + (0.8 if hints else 0), f'Sightline: {reply}')

        cam(None)   # the 1.5x full view
        orders = []   # (label, PayPal order ID) for the 'proof' step
        for step in SCRIPT:
            kind = step[0]
            print(kind, '|', str(step[1] if len(step) > 1 else kind)[:70])
            if kind == 'title':
                page.evaluate("document.getElementById('demo-beat')?.remove()")
                overlay(step[1], step[2])
                wav, dur = tts(step[3], 'narrator')
                hold(wav, dur + (2.0 if step is SCRIPT[-1] else 0), step[3])
                page.evaluate("document.getElementById('demo-title').remove()")
            elif kind == 'narrate':
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur, step[1])
            elif kind == 'beat':  # chapter: a short silent full-screen card (its text is the caption too)
                overlay(step[1], '')
                hold(None, 2.0, step[1])
                page.evaluate("document.getElementById('demo-title').remove()")
            elif kind == 'banner':  # old style: a headline banner over the live app
                page.evaluate('''(t) => { let d = document.getElementById('demo-beat');
                    if (!d) { d = document.createElement('div'); d.id = 'demo-beat'; document.documentElement.append(d);
                      d.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:98;'
                        + 'background:#0b1f3a;color:#fff;font:700 36px system-ui;padding:12px 28px;border-radius:14px;'
                        + 'box-shadow:0 6px 24px rgba(0,0,0,.35);max-width:90vw;text-align:center'; }
                    d.textContent = t; }''', step[1])
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur, step[1])
            elif kind == 'card':  # ('card', headline, image file or None, [list items], narration)
                import base64
                img = ''
                if step[2]:
                    img = 'data:image/png;base64,' + base64.b64encode((ROOT / 'demo/assets' / step[2]).read_bytes()).decode()
                wav, dur = tts(step[4], 'narrator') if step[4] else (None, 2.6)
                # list items light up one by one as the narration reaches them
                page.evaluate('''([h, img, items, ms]) => { const d = document.createElement('div'); d.id = 'demo-card';
                    d.style.cssText = 'position:fixed;inset:0;z-index:99;background:#0b1f3a;color:#fff;display:flex;gap:56px;'
                      + 'align-items:center;justify-content:center;padding:60px;font:400 30px/1.4 system-ui';
                    const text = document.createElement('div'); text.style.maxWidth = img ? '640px' : '1100px';
                    const t = document.createElement('div'); t.textContent = h; t.style.cssText = 'font:700 52px/1.15 system-ui;margin-bottom:28px';
                    text.append(t);
                    if (items.length) { const ol = document.createElement('ol'); ol.style.cssText = 'margin:0;padding-left:1.3em';
                      items.forEach((x, k) => { const li = document.createElement('li'); li.textContent = x;
                        li.style.cssText = 'margin:10px 0;opacity:.25;transition:opacity .4s'; ol.append(li);
                        setTimeout(() => { li.style.opacity = 1; }, 300 + k * ms / items.length); });
                      text.append(ol); }
                    if (img) { const i = document.createElement('img'); i.src = img; i.alt = '';
                      i.style.cssText = 'max-width:820px;max-height:780px;border-radius:18px;box-shadow:0 12px 48px rgba(0,0,0,.5)';
                      d.append(i); }
                    d.append(text); document.documentElement.append(d); }''', [step[1], img, step[3], dur * 900])
                page.wait_for_timeout(300)
                hold(wav, dur + (0.6 if wav else 0), step[4] or step[1])
                page.evaluate("document.getElementById('demo-card').remove()")
            elif kind == 'hidden':  # off-camera reset between beats (e.g. empty the cart); not recorded
                page.evaluate('''(t) => fetch('/api/turn', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: t})})''', step[1])
                page.wait_for_timeout(400)
            elif kind == 'note_order':  # ('note_order', label): remember the PayPal order ID on screen
                orders.append((step[1], page.inner_text('#pp-id').strip()))
            elif kind == 'proof':  # ('proof', narration): live GET /v2/checkout/orders/{id} from the PayPal sandbox
                rows = []
                for label, oid in orders:
                    o = paypal.get_order(oid)
                    auth = o['purchase_units'][0]['payments']['authorizations'][0]
                    excerpt = {'id': o['id'], 'status': o['status'], 'purchase_units': [{'payments': {'authorizations': [
                        {'id': auth['id'], 'status': auth['status'], 'amount': auth['amount']}]}}]}
                    rows.append([label, f'GET {paypal.API}/v2/checkout/orders/{oid}   200 OK', json.dumps(excerpt, indent=2)])
                page.evaluate('''(rows) => { const d = document.createElement('div'); d.id = 'demo-card';
                    d.style.cssText = 'position:fixed;inset:0;z-index:99;background:#0b1f3a;color:#fff;display:flex;'
                      + 'flex-direction:column;justify-content:center;padding:0 70px;gap:22px;font:400 24px system-ui';
                    const h = document.createElement('div'); h.textContent = 'PayPal sandbox API, queried at the end of this recording';
                    h.style.font = '700 40px system-ui'; d.append(h);
                    const row = document.createElement('div'); row.style.cssText = 'display:flex;gap:28px'; d.append(row);
                    for (const [label, call, res] of rows) { const b = document.createElement('div');
                      b.style.cssText = 'flex:1;background:#06101f;border-radius:14px;padding:18px 24px;border-top:8px solid #ffb800';
                      b.innerHTML = '<div style="font:700 28px system-ui;margin-bottom:6px"></div>'
                        + '<div style="font:400 17px ui-monospace,Consolas,monospace;opacity:.75;word-break:break-all"></div>'
                        + '<pre style="font:500 19px/1.3 ui-monospace,Consolas,monospace;color:#ffd666;margin:10px 0 0;white-space:pre"></pre>';
                      [label, call, res].forEach((x, k) => { b.children[k].textContent = x; }); row.append(b); }
                    document.documentElement.append(d); }''', rows)
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur + 1.0, step[1])
                page.evaluate("document.getElementById('demo-card').remove()")
            elif kind == 'api':  # ('api', path, json body): off camera, not recorded
                page.evaluate('''([u, b]) => fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(b)})''', [step[1], step[2]])
                page.wait_for_timeout(300)
            elif kind == 'setup':
                wav, dur = tts(step[1], 'narrator')
                page.check('input[name=screen_reader][value=yes]')
                for sel in ('#setup-pin', '#setup-pin2'):
                    page.fill(sel, '')
                    page.type(sel, '1234', delay=120)
                page.locator('#setup-form [type=submit]').click()
                page.wait_for_timeout(600)
                page.evaluate('''() => fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contact_name: 'Alex', contact_email: 'alex@example.com',
                                          approval_threshold: '75.00', verbosity: 'brief', current_pin: '1234'})})''')
                page.wait_for_timeout(600)
                page.reload()   # fresh page: the conversation opens with the saved settings, contact included
                page.wait_for_selector('#log .turn')
                cam(None)
                page.evaluate("document.getElementById('settings-more').open = true")
                cam('#set-threshold', 1.15)
                callout('#set-threshold', 'Alex approves orders over $75')
                hold(wav, dur, step[1])
                page.evaluate("document.getElementById('settings-more').open = false")
                cam(None)
            elif kind == 'say':   # ('say', words[, voiced-sentence hints[, camera actions after the reply]])
                submit('#message', step[1], step[1], *step[2:])
            elif kind == 'pin':
                submit('#pin', step[1], 'types the PIN (never spoken aloud)', *step[2:])
            elif kind == 'still':  # ('still', seconds, caption)
                hold(None, step[1], step[2])
            elif kind in ('cam', 'callout', 'dark'):
                do(step)
            elif kind == 'captured':  # the page captures by itself when the undo window ends; the wait is cut
                overlay('10 seconds later', 'No undo, so Sightline asks PayPal to capture.')
                a = now()
                page.wait_for_timeout(1300)
                segments.append((a, now(), None, '10 seconds later: no undo, so Sightline asks PayPal to capture.'))
                page.evaluate("document.getElementById('demo-title').remove()")
                page.wait_for_function('''() => { const t = [...document.querySelectorAll('#log .turn')].pop();
                    return t && /PayPal captured/.test(t.textContent); }''', timeout=60000)
                page.wait_for_timeout(250)
                reply = last_reply()
                reply = key_sentences(reply, step[1] if len(step) > 1 else None)
                for action in step[2:]:
                    do(action)
                wav, dur = tts(reply, 'sightline')
                hold(wav, dur, f'Sightline: {reply}')
            elif kind == 'photo':  # ('photo', demo/assets image, voiced hints[, camera actions]): the shopper's phone photo
                import base64
                img = 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'demo/assets' / step[1]).read_bytes()).decode()
                page.evaluate('''(src) => { const d = document.createElement('div'); d.id = 'demo-phone';
                    d.style.cssText = 'position:fixed;inset:0;z-index:99;background:rgba(11,31,58,.75);display:flex;'
                      + 'align-items:center;justify-content:center;gap:28px;font:600 26px system-ui;color:#fff';
                    d.innerHTML = '<div>The delivery photo</div><img alt="" style="width:420px;height:640px;object-fit:cover;'
                      + 'border:10px solid #111;border-radius:28px">';
                    d.querySelector('img').src = src; document.documentElement.append(d); }''', img)
                n = page.locator('#log .turn').count()
                a = now()
                page.wait_for_timeout(3000)
                segments.append((a, now(), None, 'The shopper chooses a photo of the delivery.'))
                page.evaluate("document.getElementById('demo-phone').remove()")
                page.set_input_files('#package-photo', str(ROOT / 'demo/assets' / step[1]))
                wait_turn(n)
                reply = key_sentences(last_reply(), step[2])
                for action in step[3:]:
                    do(action)
                wav, dur = tts(reply, 'sightline')
                hold(wav, dur + 0.5, f'Sightline: {reply}')
            elif kind == 'approve':  # Alex's side, shown as a phone-sized overlay on the same recording
                href = page.evaluate('''() => [...document.querySelectorAll('#log a[href^="/approve/"]')].pop().getAttribute('href')''')
                page.evaluate('''(h) => { const d = document.createElement('div'); d.id = 'demo-phone';
                    d.style.cssText = 'position:fixed;inset:0;z-index:99;background:rgba(11,31,58,.75);display:flex;'
                      + 'align-items:center;justify-content:center;gap:28px;font:600 26px system-ui;color:#fff';
                    d.innerHTML = '<div>Alex\\'s phone</div><iframe title="Approval page" style="width:420px;height:760px;'
                      + 'border:10px solid #111;border-radius:28px;background:#fff"></iframe>';
                    const f = d.querySelector('iframe'); f.style.width = '520px'; f.style.height = '800px';
                    f.onload = () => { f.contentDocument.documentElement.style.zoom = '1.3'; };
                    f.src = h; document.documentElement.append(d); }''', href)
                page.wait_for_timeout(1500)
                wav, dur = tts(step[1], 'narrator')
                a = now()
                page.wait_for_timeout(int(dur * 600))
                choice = 'Decline this order' if 'decline' in step[2:] else 'Approve this order'
                btn = page.frame_locator('#demo-phone iframe').get_by_role('button', name=choice)
                btn.scroll_into_view_if_needed()
                btn.evaluate("b => { b.style.outline = '6px solid #ffb800'; b.style.outlineOffset = '3px'; }")
                page.wait_for_timeout(700)
                btn.click()
                page.wait_for_timeout(max(1200, int(dur * 400) + 350))
                segments.append((a, now(), wav, step[1]))
                page.evaluate("document.getElementById('demo-phone').remove()")
        video = page.video.path()
        ctx.close()
        browser.close()
    return Path(video), segments


# ---------- editing ----------
def ff(*args):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], check=True, cwd=OUT)


def stamp(t):
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def cues(caption, start, dur, words_per_cue=14):
    if not caption:   # a silent, uncaptioned moment: an empty SRT block would swallow the next caption
        return
    words = caption.split()
    chunks = [' '.join(words[i:i + words_per_cue]) for i in range(0, len(words), words_per_cue)] or ['']
    total = sum(len(c) for c in chunks) or 1
    t = start
    for c in chunks:
        d = dur * len(c) / total
        yield t, t + d, c
        t += d


def edit(video, segments):
    parts, srt, t = [], [], 0.0
    for i, (a, b, wav, caption) in enumerate(segments):
        dur = b - a
        seg = f'seg{i:03d}.mp4'
        audio = ['-i', str(wav)] if wav else ['-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono']
        ff('-ss', f'{a:.3f}', '-i', str(video), *audio, '-t', f'{dur:.3f}', '-filter_complex', '[1:a]apad[a]',
           '-map', '0:v', '-map', '[a]', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-ar', '44100', seg)
        parts.append(seg)
        srt += list(cues(caption, t, dur))
        t += dur
    (OUT / 'parts.txt').write_text(''.join(f"file '{p}'\n" for p in parts))
    (OUT / 'sightline_demo.srt').write_text(
        ''.join(f'{n}\n{stamp(a)} --> {stamp(b)}\n{c}\n\n' for n, (a, b, c) in enumerate(srt, 1)), encoding='utf-8')
    ff('-f', 'concat', '-safe', '0', '-i', 'parts.txt', '-c', 'copy', 'joined.mp4')
    # captions live in their own bar under the app (libass units: 288 = frame height, so the bar is ~37 high)
    ff('-i', 'joined.mp4', '-vf', f"pad=1920:1080:0:0:color=0x0b1f3a,subtitles=sightline_demo.srt:force_style='FontSize=10,"
       "BorderStyle=1,Outline=0,Shadow=0,MarginV=8,PrimaryColour=&H00FFFFFF'",
       '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-c:a', 'copy', 'sightline_demo.mp4')
    for p in parts:
        (OUT / p).unlink()
    print(f'done: {OUT / "sightline_demo.mp4"} ({t:.0f} s)')


def prefetch():
    """Voice every line known in advance before recording, so real-time steps (the 10 s undo window) aren't
    slowed by speech generation."""
    for step in SCRIPT:
        if step[0] in ('title', 'narrate', 'setup', 'card', 'proof') and step[-1]:   # silent cards have no narration
            tts(step[-1], 'narrator')
        elif step[0] == 'approve':
            tts(step[1], 'narrator')
        elif step[0] == 'say':
            tts(step[1], 'you')
    tts('In 10 seconds Sightline asks PayPal to take the payment.', 'sightline')   # voiced right after the PIN


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    SCRIPT = SCRIPTS[sys.argv[1] if len(sys.argv) > 1 else 'full']
    prefetch()
    server = start_server()
    try:
        video, segments = record()
    finally:
        server.kill()
    edit(video, segments)
