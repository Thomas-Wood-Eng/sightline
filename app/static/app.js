// Sightline front end. Plain JS. Each reply is appended to the log ONCE, complete, so screen readers read it once.
const $ = (id) => document.getElementById(id);
const log = $('log'), msg = $('message'), talk = $('talk'), pinForm = $('pin-form'), pinInput = $('pin');
let mode = 'screen_reader', state = 'idle', busy = false;

// ---- earcons: short, quiet WebAudio tones ----
let audio;
function tone(freqs, dur = 0.06, gain = 0.05) {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    freqs.forEach((f, i) => {
      const o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + i * dur;
      o.frequency.value = f; g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(audio.destination); o.start(t); o.stop(t + dur);
    });
  } catch (e) { /* sound is a bonus, never required */ }
}
const earcon = {
  heard: () => tone([880], 0.05),
  working: () => tone([440, 440], 0.07, 0.03),
  success: () => tone([660, 990], 0.08),
  error: () => tone([220], 0.09),
};

// ---- output ----
function speak(text) {
  if (mode !== 'voice' || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function setMode(m) {
  mode = m;
  // never both: when the app speaks, the log stops announcing
  log.setAttribute('aria-live', m === 'voice' ? 'off' : 'polite');
  if (m !== 'voice' && 'speechSynthesis' in window) speechSynthesis.cancel();
}

function append(you, say, lines = []) {
  const turn = document.createElement('div');
  turn.className = 'turn';
  if (you) {
    const p = document.createElement('p'); p.className = 'you'; p.textContent = 'You: ' + you; turn.append(p);
  }
  const s = document.createElement('p'); s.className = 'say'; s.textContent = say; turn.append(s);
  lines.forEach((l) => {
    const p = document.createElement('p');
    p.className = /^Total:/.test(l) ? 'line total' : 'line';
    p.textContent = l; turn.append(p);
  });
  log.append(turn);  // one insertion per reply
  turn.scrollIntoView({ block: 'nearest' });
  speak([say, ...lines].join(' '));
}

function showItem(f) {
  if (!f) return;
  const img = $('item-img');
  $('item-name').textContent = f.name;
  if (f.image) { img.hidden = false; img.alt = f.alt; img.src = f.image; } else img.hidden = true;
  $('item').hidden = false; $('no-item').hidden = true;
}
$('item-img').addEventListener('error', (e) => { e.target.hidden = true; });

function setState(s) {
  const was = state; state = s;
  const showPin = s === 'awaiting_pin';
  pinForm.hidden = !showPin;
  if (showPin && was !== 'awaiting_pin') pinInput.focus();
  if (!showPin && document.activeElement === pinInput) msg.focus();
  if (s === 'captured' && was !== 'captured') earcon.success();
}

// ---- requests ----
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Something went wrong. Please try again.');
  return j;
}

async function turn(url, body, youText) {
  if (busy) return;
  busy = true; earcon.heard();
  const slow = setTimeout(earcon.working, 1000);
  try {
    const r = await post(url, body);
    append(youText, r.say, r.lines);
    showItem(r.focus);
    setState(r.state);
    if (r.action === 'link') location.assign('/link/start');
  } catch (e) {
    earcon.error(); append(youText, e.message);
  } finally { clearTimeout(slow); busy = false; }
}

const send = (text) => turn('/api/turn', { text }, text);

$('ask').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = msg.value.trim();
  if (!text) return;
  msg.value = '';
  // a PIN typed into the message box is never echoed on screen
  const hide = state === 'awaiting_pin' && /^[\d\s-]{4,}$/.test(text);
  turn('/api/turn', { text }, hide ? '(hidden)' : text);
});

pinForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const pin = pinInput.value.trim();
  pinInput.value = '';
  turn('/api/pin', { pin }, 'PIN entered');
});
$('pin-cancel').addEventListener('click', () => send('cancel'));

// ---- push to talk (Web Speech API, Chrome and Edge) ----
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
const voiceStatus = (t) => { $('voice-status').textContent = t; };

async function toggleTalk() {
  if (rec) { rec.stop(); return; }
  if (!SR) { voiceStatus('Voice input is not available in this browser. Please type in the message box instead.'); msg.focus(); return; }
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  rec = new SR();
  rec.lang = 'en-US'; rec.interimResults = false; rec.maxAlternatives = 1;
  try {  // on-device recognition when the browser offers it (Chromium 139+)
    if (SR.available && (await SR.available({ langs: ['en-US'], processLocally: true })) === 'available') rec.processLocally = true;
  } catch (e) { /* fall back to the default service */ }
  rec.onresult = (e) => send(e.results[0][0].transcript);
  rec.onerror = (e) => {
    if (e.error === 'aborted') return;
    earcon.error();
    voiceStatus(e.error === 'no-speech' ? 'I did not hear anything. Press Talk to try again, or type.'
      : 'Voice input did not work (' + e.error + '). Please type in the message box instead.');
  };
  rec.onend = () => { rec = null; talk.setAttribute('aria-pressed', 'false'); talk.textContent = 'Talk (Alt+Shift+M)'; };
  voiceStatus('');
  try {
    rec.start(); earcon.heard();
    talk.setAttribute('aria-pressed', 'true'); talk.textContent = 'Listening. Press to stop (Alt+Shift+M)';
  } catch (e) { rec = null; voiceStatus('Voice input could not start. Please type in the message box instead.'); }
}
talk.addEventListener('click', toggleTalk);

// ---- shortcuts: modifier keys only (single keys clash with screen reader quick keys) ----
document.addEventListener('keydown', (e) => {
  if (e.altKey && e.shiftKey && e.code === 'KeyM') { e.preventDefault(); toggleTalk(); }
  else if (e.altKey && e.shiftKey && e.code === 'KeyR') { e.preventDefault(); send('repeat'); }
  else if (e.key === 'Escape') {
    if ('speechSynthesis' in window && speechSynthesis.speaking) speechSynthesis.cancel();
    else if (rec) rec.abort();
    else if (state === 'awaiting_confirm' || state === 'awaiting_pin') send('cancel');
  }
});

// ---- setup and settings ----
function fillSettings(s) {
  setMode(s.output_mode);
  setState(s.state);
  $('setup').hidden = s.onboarded;
  const f = $('settings-form');
  f.output_mode.value = s.output_mode;
  f.per_order_cap.value = s.per_order_cap; f.daily_cap.value = s.daily_cap;
  $('link-status').textContent = s.linked ? 'PayPal is linked.' : 'PayPal is not linked yet.';
  $('link-btn').textContent = s.linked ? 'Link PayPal again' : 'Link PayPal';
}

$('setup-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target, status = $('setup-status');
  if (!/^\d{4}$/.test(f.pin.value)) { status.textContent = 'Error: the PIN must be exactly 4 digits.'; f.pin.focus(); return; }
  if (f.pin.value !== $('setup-pin2').value) { status.textContent = 'Error: the two PINs do not match.'; $('setup-pin2').focus(); return; }
  try {
    const s = await post('/api/onboarding', { screen_reader: f.screen_reader.value === 'yes', pin: f.pin.value,
      per_order_cap: f.per_order_cap.value, daily_cap: f.daily_cap.value });
    f.reset(); fillSettings(s);
    append(null, 'Setup saved. ' + s.summary + ' What would you like to shop for?');
    msg.focus();
  } catch (err) { status.textContent = 'Error: ' + err.message; }
});

$('settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target, status = $('settings-status');
  const body = { output_mode: f.output_mode.value || null, per_order_cap: f.per_order_cap.value || null,
    daily_cap: f.daily_cap.value || null, new_pin: f.new_pin.value || null, current_pin: f.current_pin.value || null };
  try {
    const s = await post('/api/settings', body);
    f.new_pin.value = ''; f.current_pin.value = '';
    fillSettings(s); status.textContent = 'Saved. ' + s.summary;
  } catch (err) { status.textContent = 'Error: ' + err.message; f.current_pin.focus(); }
});

(async function init() {
  const s = await fetch('/api/settings').then((r) => r.json());
  fillSettings(s);
  const link = new URLSearchParams(location.search).get('link');
  if (link) history.replaceState(null, '', '/');
  const linkMsg = { done: 'PayPal is linked. You can now check out.', cancelled: 'PayPal linking was cancelled. Nothing changed.',
    error: 'PayPal linking did not work. Please try Link PayPal again.' }[link];
  append(null, (linkMsg ? linkMsg + ' ' : '') + (s.onboarded ? 'Welcome back. What would you like to shop for?'
    : 'Welcome to Sightline. Please answer the Setup questions first, or start by typing what you want.'));
  if (s.onboarded) msg.focus();
})();
