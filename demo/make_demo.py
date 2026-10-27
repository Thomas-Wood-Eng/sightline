"""Render the pre-testing demo video from the REAL app:  python demo/make_demo.py  ->  demo/out/sightline_demo.mp4 + .srt

1. starts the app (with the pre-approved sandbox wallet, so checkout hits the real PayPal sandbox),
2. drives it in Chromium with Playwright and records the screen,
3. voices narrator, shopper and Sightline with Gemini TTS (free tier; cached in demo/out/tts/),
4. cuts out the seconds spent generating speech, lays each clip on its segment, burns captions with ffmpeg.
Shopper input is typed by the script (narrated as speech); everything the app says and does is real.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
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

SCRIPT = [
    ('title', 'Sightline', 'Shop by voice. Hear every dollar before it moves.',
     'This is Sightline: a voice and keyboard first shopping assistant for blind and low-vision people, built on PayPal. '
     'This is an early prototype, recorded before testing with blind users.'),
    ('narrate', 'Blind shoppers can often find a product, then lose it at checkout to pop-ups, captchas and unlabelled buttons. '
                'Sightline turns the whole purchase into a conversation.'),
    ('setup', 'Setup happens once: a four-digit PIN, and spending limits that can only be changed in settings. '
              "PayPal was linked beforehand, on PayPal's own login page."),
    ('narrate', 'Allergies are a hard filter in code, not a guess by the AI.'),
    ('say', 'I need a snack for my kid. She has a nut allergy.'),
    ('say', 'Find me a hoodie.'),
    ('say', 'Tell me about the first one.'),
    ('say', 'What colour is it exactly?'),
    ('say', 'Compare the first two.'),
    ('say', 'Add the first one.'),
    ('say', 'Check out.'),
    ('narrate', "Every amount you just heard was read from PayPal's own order, not written by the AI. "
                'The money is only on hold until the shopper confirms and types their PIN.'),
    ('say', 'Confirm.'),
    ('pin', '1234'),
    ('narrate', 'Safety limits are enforced by code too.'),
    ('say', 'Find a rain jacket.'),
    ('say', 'Add the first one.'),
    ('say', 'Find jeans.'),
    ('say', 'Add the first one.'),
    ('say', 'Check out.'),
    ('say', 'Remove the jeans.'),
    ('say', 'Check out.'),
    ('say', 'Cancel.'),
    ('title', 'The AI suggests. It never holds the keys.', 'Next: testing with blind and low-vision shoppers.',
     'The agent does the clicking. The person makes every decision. Next, testing with blind and low-vision shoppers.'),
]


# ---------- speech ----------
def tts(text, who):
    """Gemini TTS -> cached wav path. The API returns a complete WAV file, so the bytes are saved as-is."""
    from google.genai import types
    from app.llm import client
    TTS.mkdir(parents=True, exist_ok=True)
    path = TTS / (hashlib.sha1(f'{who}|{text}'.encode()).hexdigest()[:16] + '.wav')
    if not path.exists():
        prompt = {'narrator': 'Read like a calm documentary narrator: ', 'you': 'Say naturally, like a person talking to an assistant: ',
                  'sightline': 'Read clearly and briskly, like a helpful screen reader voice: '}[who] + text
        for attempt in range(5):
            try:
                r = client().models.generate_content(
                    model='gemini-3.8-flash-tts', contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=['AUDIO'], speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICES[who])))))
                path.write_bytes(r.candidates[0].content.parts[0].inline_data.data)
                break
            except Exception as e:  # free tier: back off on 429/503
                print(f'  tts retry {attempt + 1}: {str(e)[:80]}')
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f'TTS failed for: {text[:60]}')
    with wave.open(str(path)) as w:
        return path, w.getnframes() / w.getframerate()


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
        ctx = browser.new_context(viewport={'width': 1280, 'height': 720}, record_video_dir=str(OUT / 'raw'),
                                  record_video_size={'width': 1280, 'height': 720})
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

        def submit(selector, text, voiced):
            n = page.locator('#log .turn').count()
            wav, dur = tts(voiced, 'you')
            a = now()
            page.click(selector)
            page.keyboard.type(text, delay=max(20, min(90, int(dur * 800 / max(len(text), 1)))))
            page.keyboard.press('Enter')
            page.wait_for_function(f"document.querySelectorAll('#log .turn').length > {n}", timeout=30000)
            page.wait_for_timeout(250)
            segments.append((a, now(), wav, f'You: {voiced}'))
            reply = last_reply()
            wav, dur = tts(reply, 'sightline')  # generated while the screen is static; this gap is cut later
            hold(wav, dur, f'Sightline: {reply}')

        for step in SCRIPT:
            kind = step[0]
            print(kind, '|', (step[-1] if kind != 'pin' else 'PIN')[:70])
            if kind == 'title':
                overlay(step[1], step[2])
                wav, dur = tts(step[3], 'narrator')
                hold(wav, dur, step[3])
                page.evaluate("document.getElementById('demo-title').remove()")
            elif kind == 'narrate':
                wav, dur = tts(step[1], 'narrator')
                hold(wav, dur, step[1])
            elif kind == 'setup':
                wav, dur = tts(step[1], 'narrator')
                a = now()
                page.check('input[name=screen_reader][value=yes]')
                for sel in ('#setup-pin', '#setup-pin2'):
                    page.fill(sel, '')
                    page.type(sel, '1234', delay=120)
                page.locator('#setup-form [type=submit]').click()
                page.wait_for_timeout(max(0, int(dur * 1000) - int((now() - a) * 1000)) + 350)
                segments.append((a, now(), wav, step[1]))
            elif kind == 'say':
                submit('#message', step[1], step[1])
            elif kind == 'pin':
                submit('#pin', step[1], 'Types the PIN.')
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
    ff('-i', 'joined.mp4', '-vf', "subtitles=sightline_demo.srt:force_style='FontSize=18,BorderStyle=3,Outline=1,MarginV=18'",
       '-c:a', 'copy', 'sightline_demo.mp4')
    for p in parts:
        (OUT / p).unlink()
    print(f'done: {OUT / "sightline_demo.mp4"} ({t:.0f} s)')


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    server = start_server()
    try:
        video, segments = record()
    finally:
        server.kill()
    edit(video, segments)
