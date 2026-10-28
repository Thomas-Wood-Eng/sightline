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
    ('beat', 'Allergies are a hard filter.'),
    ('say', 'I need a snack for my kid. She has a nut allergy.', ['Showing only']),
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
    ('title', 'The AI suggests. It never holds the keys.', 'Sightline: PayPal AI Hackathon 2026',
     'The AI suggests. It never holds the keys. Sightline.'),
]
SCRIPTS = {'ad': AD, 'full': INTRO + ALLERGY + HOODIE + PAY + SCAM + [('say', 'Remove the headphones.')] + APPROVAL + REFUND + OUTRO,
           # Devpost cut, must stay under 3 minutes: the problem, one purchase, the trusted contact and undo
           'short': [
               ('title', 'Sightline', 'Shop by voice. Hear every dollar before it moves.',
                'Blind shoppers can find a product online, then lose it at checkout. Sightline is a voice and keyboard '
                'first shopping assistant, built on PayPal. An early prototype.'),
               ('setup', "Setup happens once: a PIN, spending limits, and a trusted contact. Replies play at "
                         'screen-reader speed.'),
               ('say', 'Find me a hoodie.', ['results']), ('say', 'Add the first one.', ['Which size']),
               ('say', 'Medium.', ['Added']),
               ('say', 'Check out.'),   # the one Readback voiced in full
               ('narrate', 'Those numbers came from PayPal, not the AI. Nothing moves until the shopper confirms with a PIN.'),
               ('say', 'Confirm.', ['PIN']), ('pin', '1234', ['10 seconds']), ('captured',),
               ('narrate', 'Above a set amount, a trusted contact approves first.'),
               ('say', 'Find a rain jacket.', ['results']), ('say', 'Add it.', ['Added']),
               ('say', 'Check out.', ['Total:', 'Sent to Alex']),
               APPROVAL[4],
               ('say', 'Confirm.', ['PIN']), ('pin', '1234', ['10 seconds']),
               ('say', 'Undo.', ['Undone', 'Nothing was charged']),
               ('title', 'The AI suggests. It never holds the keys.', 'github.com/Thomas-Wood-Eng/sightline',
                'And for ten seconds, they can still undo. The AI suggests. It never holds the keys.'),
           ]}
SCRIPT = SCRIPTS['full']


# ---------- speech ----------
# Narrator and shopper: Gemini TTS (most natural; free tier = 10 clips/day per model, so rotate models and cache).
# Sightline: local Kokoro (unlimited; its even delivery suits a screen-reader-style assistant). If Gemini's daily
# quota is gone, Kokoro voices stand in so a render always finishes; the next run retries Gemini for those clips.
GEMINI_TTS = ['gemini-3.8-flash-tts', 'gemini-3.1-flash-tts-preview', 'gemini-3.8-flash-lite-tts', 'gemini-2.5-flash-preview-tts']
KOKORO_VOICES = {'sightline': 'af_heart', 'narrator': 'bm_george', 'you': 'am_puck'}
_spent = set()   # Gemini models whose daily quota ran out this run
_kokoro = None


def _gemini(text, who, path):
    from google.genai import types
    from app.llm import client
    prompt = {'narrator': 'Read like a calm, warm documentary narrator: ',
              'you': 'Say naturally, like a person casually talking to a voice assistant: '}[who] + text
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


def tts(text, who):
    """-> (cached wav path, seconds). Orpheus first, then Gemini (narrator/shopper), then local Kokoro."""
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
    if path is None:
        if not kok.exists():
            _kokoro_tts(text, who, kok)
        path = kok
    if who == 'sightline':  # screen-reader users listen fast; 1.3x keeps it followable for sighted viewers
        fast = path.with_name(path.stem + f'.x{SIGHTLINE_SPEED}.wav')
        if not fast.exists():
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path),
                            '-filter:a', f'atempo={SIGHTLINE_SPEED}', str(fast)], check=True)
        path = fast
    with wave.open(str(path)) as w:
        return path, w.getnframes() / w.getframerate()


SIGHTLINE_SPEED = 1.3


# ---------- recording ----------
def start_server():
    vault = json.loads((ROOT / 'spike_state.json').read_text())['vault_id']
    env = dict(os.environ, DEMO_VAULT_ID=vault, PYTHONIOENCODING='utf-8')
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
    segments = []  # (start_s, end_s, wav or None, caption)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1920, 'height': 1080}, record_video_dir=str(OUT / 'raw'),
                                  record_video_size={'width': 1920, 'height': 1080})
        page = ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0
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
                d.children[0].textContent = t; d.children[1].textContent = s; document.body.append(d); }''', [title, sub])

        def last_reply():
            return page.evaluate('''() => { const t = [...document.querySelectorAll('#log .turn')].pop();
                return [...t.querySelectorAll('p:not(.you)')].map(p => p.textContent).join(' '); }''')

        def wait_turn(n):
            page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=60000)
            page.evaluate('window.scrollTo(0, 0)')  # keep the conversation, product and banner in frame
            page.wait_for_timeout(250)

        def key_sentences(reply, hints):
            """Ad cut: voice only the sentences that carry the point; the full reply stays on screen."""
            parts = re.split(r'(?<=[.!?])\s+', reply)
            picked = [p for p in parts if any(h.lower() in p.lower() for h in hints)]
            return ' '.join(picked or parts[:1])

        def submit(selector, text, voiced, hints=None):
            n = page.locator('#log .turn').count()
            wav, dur = tts(voiced, 'you')
            a = now()
            page.click(selector)
            page.keyboard.type(text, delay=max(20, min(90, int(dur * 800 / max(len(text), 1)))))
            page.keyboard.press('Enter')
            wait_turn(n)
            segments.append((a, now(), wav, f'You: {voiced}'))
            reply = last_reply()
            if hints:
                reply = key_sentences(reply, hints)
            wav, dur = tts(reply, 'sightline')  # generated while the screen is static; this gap is cut later
            hold(wav, dur + (0.8 if hints else 0), f'Sightline: {reply}')

        for step in SCRIPT:
            kind = step[0]
            print(kind, '|', str(step[1] if len(step) > 1 else kind)[:70])
            if kind == 'title':
                page.evaluate("document.getElementById('demo-beat')?.remove()")
                overlay(step[1], step[2])
                wav, dur = tts(step[3], 'narrator')
                hold(wav, dur, step[3])
                page.evaluate("document.getElementById('demo-title').remove()")
            elif kind == 'narrate':
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur, step[1])
            elif kind == 'beat':  # ad cut: a headline banner over the live app, voiced by the narrator
                page.evaluate('''(t) => { let d = document.getElementById('demo-beat');
                    if (!d) { d = document.createElement('div'); d.id = 'demo-beat'; document.body.append(d);
                      d.style.cssText = 'position:fixed;top:18px;left:50%;transform:translateX(-50%);z-index:98;'
                        + 'background:#0b1f3a;color:#fff;font:700 40px system-ui;padding:14px 30px;border-radius:14px;'
                        + 'box-shadow:0 6px 24px rgba(0,0,0,.35);max-width:90vw;text-align:center'; }
                    d.textContent = t; }''', step[1])
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur, step[1])
            elif kind == 'hidden':  # off-camera reset between beats (e.g. empty the cart); not recorded
                page.evaluate('''(t) => fetch('/api/turn', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: t})})''', step[1])
                page.wait_for_timeout(400)
            elif kind == 'setup':
                wav, dur = tts(step[1], 'narrator')
                a = now()
                page.check('input[name=screen_reader][value=yes]')
                for sel in ('#setup-pin', '#setup-pin2'):
                    page.fill(sel, '')
                    page.type(sel, '1234', delay=120)
                page.locator('#setup-form [type=submit]').click()
                page.wait_for_timeout(600)
                page.evaluate('''() => fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contact_name: 'Alex', contact_email: 'alex@example.com',
                                          approval_threshold: '75.00', verbosity: 'brief', current_pin: '1234'})})''')
                page.wait_for_timeout(max(0, int(dur * 1000) - int((now() - a) * 1000)) + 350)
                segments.append((a, now(), wav, step[1]))
            elif kind == 'say':
                submit('#message', step[1], step[1], step[2] if len(step) > 2 else None)
            elif kind == 'pin':
                submit('#pin', step[1], 'Types the PIN.', step[2] if len(step) > 2 else None)
            elif kind == 'captured':  # the page captures by itself when the undo window ends; the wait is cut
                page.wait_for_function('''() => { const t = [...document.querySelectorAll('#log .turn')].pop();
                    return t && /PayPal captured/.test(t.textContent); }''', timeout=60000)
                page.wait_for_timeout(250)
                reply = last_reply()
                wav, dur = tts(reply, 'sightline')
                hold(wav, dur, f'Sightline: {reply}')
            elif kind == 'approve':  # Alex's side, shown as a phone-sized overlay on the same recording
                href = page.evaluate('''() => [...document.querySelectorAll('#log a[href^="/approve/"]')].pop().getAttribute('href')''')
                page.evaluate('''(h) => { const d = document.createElement('div'); d.id = 'demo-phone';
                    d.style.cssText = 'position:fixed;inset:0;z-index:99;background:rgba(11,31,58,.75);display:flex;'
                      + 'align-items:center;justify-content:center;gap:28px;font:600 26px system-ui;color:#fff';
                    d.innerHTML = '<div>Alex\\'s phone</div><iframe title="Approval page" style="width:420px;height:640px;'
                      + 'border:10px solid #111;border-radius:28px;background:#fff"></iframe>';
                    d.querySelector('iframe').src = h; document.body.append(d); }''', href)
                page.wait_for_timeout(1500)
                wav, dur = tts(step[1], 'narrator')
                a = now()
                page.wait_for_timeout(int(dur * 600))
                page.frame_locator('#demo-phone iframe').get_by_role('button', name='Approve this order').click()
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
           '-map', '0:v', '-map', '[a]', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-ar', '44100', seg)
        parts.append(seg)
        srt += list(cues(caption, t, dur))
        t += dur
    (OUT / 'parts.txt').write_text(''.join(f"file '{p}'\n" for p in parts))
    (OUT / 'sightline_demo.srt').write_text(
        ''.join(f'{n}\n{stamp(a)} --> {stamp(b)}\n{c}\n\n' for n, (a, b, c) in enumerate(srt, 1)), encoding='utf-8')
    ff('-f', 'concat', '-safe', '0', '-i', 'parts.txt', '-c', 'copy', 'joined.mp4')
    ff('-i', 'joined.mp4', '-vf', "subtitles=sightline_demo.srt:force_style='FontSize=11,BorderStyle=3,Outline=1,MarginV=10,BackColour=&H60000000'",
       '-c:a', 'copy', 'sightline_demo.mp4')
    for p in parts:
        (OUT / p).unlink()
    print(f'done: {OUT / "sightline_demo.mp4"} ({t:.0f} s)')


def prefetch():
    """Voice every line known in advance before recording, so real-time steps (the 10 s undo window) aren't
    slowed by speech generation."""
    for step in SCRIPT:
        if step[0] in ('title', 'narrate', 'setup', 'approve', 'beat'):
            tts(step[-1], 'narrator')
        elif step[0] == 'say':
            tts(step[1], 'you')
    tts('Types the PIN.', 'you')
    tts('PIN accepted. PayPal takes the payment in 10 seconds. To stop it, say undo, or press Escape, '
        'or use the Undo button.', 'sightline')
    tts('PayPal takes the payment in 10 seconds.', 'sightline')   # the ad cut voices only this sentence


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
