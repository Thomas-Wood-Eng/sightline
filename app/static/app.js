// Sightline front end. Plain JS. Each reply is appended to the log ONCE, complete, so screen readers read it once.
const $ = (id) => document.getElementById(id);
const log = $('log'), msg = $('message'), talk = $('talk'), pinForm = $('pin-form'), pinInput = $('pin');
let mode = 'screen_reader', state = 'idle', busy = false, queued = null, lastSent = { text: '', at: 0 };
const HOLD = ['awaiting_confirm', 'awaiting_pin', 'awaiting_approval'];

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
  $('pay-status').setAttribute('aria-live', m === 'voice' ? 'off' : 'polite');
  if (m !== 'voice' && 'speechSynthesis' in window) speechSynthesis.cancel();
}

function append(you, say, lines = []) {
  const turn = document.createElement('div');
  turn.className = 'turn';
  if (you) {
    const p = document.createElement('p'); p.className = 'you'; p.textContent = 'You: ' + you; turn.append(p);
  }
  const reply = document.createElement('div'); reply.className = 'reply';
  if (lines.some((l) => /^Total:/.test(l))) reply.classList.add('readback');  // PayPal's numbers, shown as a receipt
  const s = document.createElement('p'); s.className = 'say'; s.textContent = say; reply.append(s);
  lines.forEach((l) => {
    const p = document.createElement('p');
    p.className = /^Total:/.test(l) ? 'line total' : 'line';
    const link = /^Approval link: (\/approve\/\S+)$/.exec(l);
    if (link) {  // shown instead of emailed in this prototype
      const a = document.createElement('a'); a.href = link[1]; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = 'Open the approval page (opens in a new tab)';
      p.append('Approval link: ', a);
    } else p.textContent = l;
    reply.append(p);
  });
  turn.append(reply);
  log.append(turn);  // one insertion per reply
  log.scrollTop = turn.offsetTop;  // the start of the newest reply, inside the log's own scroll; the page stays put
  speak([say, ...lines].join(' '));
}

// payment status: shown on screen, and spoken (app voice) or announced (screen reader), never both
function payStatus(text, quiet = false) {
  $('pay-status').textContent = text;
  if (text && !(quiet && 'speechSynthesis' in window && speechSynthesis.speaking)) speak(text);  // quiet: never cut a reply
}

// Escape's instant feedback, shown at once. The screen reader hears only the reply that follows ("Undone...",
// announce once); the app voice says it straight away, and the reply then replaces it.
function progress(text) {
  if (mode === 'voice') payStatus(text); else $('pay-progress').textContent = text;
}

function showItem(f) {
  if (!f) return;
  const img = $('item-img');
  $('item-name').textContent = f.name;
  $('item-price').textContent = f.price || ''; $('item-rating').textContent = f.rating || '';
  if (f.image) { img.hidden = false; img.alt = f.alt; img.src = f.image; } else img.hidden = true;
  $('item').hidden = false; $('no-item').hidden = true;
}
$('item-img').addEventListener('error', (e) => { e.target.hidden = true; });

// the PayPal panel: every word and number comes from the server (PayPal's order); not live, the reply says it already
const MARK = { done: 'Done: ', current: 'Now: ', next: 'Next: ' };
function showPayPal(p) {
  if (!p) return;
  $('link-status').textContent = p.linked ? `PayPal linked: ${p.account}` : 'Not linked yet.';
  $('link-status').classList.toggle('linked', p.linked);
  $('link-btn').textContent = p.linked ? 'Link PayPal again' : 'Link PayPal';
  const o = p.order;
  $('pp-order').hidden = !o; $('pp-none').hidden = !!o;
  if (!o) return;
  $('pp-title').textContent = o.kind === 'refund' ? 'Your return at PayPal' : 'This order at PayPal';
  $('pp-amount').textContent = o.amount || ''; $('pp-id').textContent = o.id; $('pp-status').textContent = o.status;
  $('pp-steps').replaceChildren(...o.steps.map((st, i) => {
    const li = document.createElement('li'), sr = document.createElement('span');
    const ended = o.ended && i === o.steps.length - 1;
    li.className = ended ? 'ended' : st.state;
    sr.className = 'sr'; sr.textContent = ended ? 'Ended: ' : MARK[st.state];
    li.append(sr, st.label);
    if (st.state === 'current') li.setAttribute('aria-current', 'step');
    return li;
  }));
}

let finalizeTimer = null, tick = null, paying = false;
const countdown = (t) => { $('countdown').textContent = t; };
// pay: "Paying 59.59 US dollars to ...", from the server (PayPal's amount), never computed here
function setState(s, dueIn = 0, pay = '', say = '') {
  const was = state; state = s;
  clearTimeout(finalizeTimer); clearInterval(tick);
  const box = $('undo-box');
  $('pin-amount').textContent = $('undo-amount').textContent = pay || '';
  if (s === 'undo_window') {
    // undo window: PayPal captures when it ends; until then Undo (or Escape) voids the hold.
    // The countdown updates on screen every second but is announced only at the 5-second mark (not chatty).
    paying = false; box.hidden = false; $('undo-btn').hidden = false;
    if (was !== s) $('undo-btn').focus();  // the one control that matters for the next 10 seconds
    const due = Date.now() + dueIn * 1000;
    let warned = dueIn <= 5;
    const update = () => {
      const left = Math.max(0, Math.ceil((due - Date.now()) / 1000));
      countdown(left === 1 ? 'Paying in 1 second' : `Paying in ${left} seconds`);
      if (!warned && left <= 5) {  // said once; then the line is cleared so it never sits beside a smaller number
        warned = true; const t = '5 seconds left to undo. Press Escape or Undo.'; payStatus(t, true);
        setTimeout(() => { if ($('pay-status').textContent === t) $('pay-status').textContent = ''; }, 2000);
      }
    };
    update(); tick = setInterval(update, 250);
    finalizeTimer = setTimeout(() => {
      clearInterval(tick); paying = true; $('undo-btn').hidden = true;
      countdown('Paying now…'); payStatus('Paying now.');
      turn('/api/finalize', {}, null);
    }, dueIn * 1000 + 300);
  } else if (was === 'undo_window' && say) {
    paying = false; $('undo-btn').hidden = true; countdown(say);  // the result stays in the box until the next reply
  } else { paying = false; box.hidden = true; }
  const showPin = s === 'awaiting_pin';
  pinForm.hidden = !showPin;
  // also when the PIN is already waiting and the user is still in the message box
  if (showPin && (was !== 'awaiting_pin' || document.activeElement === msg)) pinInput.focus();
  if (!showPin && document.activeElement === pinInput) msg.focus();
  if (s === 'captured' && was !== 'captured') earcon.success();
  if (s !== 'awaiting_approval') { clearInterval(approvalPoll); approvalPoll = null; }
  else if (!approvalPoll) approvalPoll = setInterval(pollApproval, APPROVAL_POLL_MS);
}

// waiting for the trusted contact: ask the server every few seconds, so their decision is said without asking.
// Never while a turn is on its way (that turn hears the decision itself), so it is said once.
let approvalPoll = null;
const APPROVAL_POLL_MS = 4000;
async function pollApproval() {
  if (busy) return;
  busy = true;
  try {
    const r = await post('/api/approval', {});
    if (r.say) { append(null, r.say, r.lines); showPayPal(r.paypal); setState(r.state, r.due_in, r.pay, r.say); }
    else if (r.state !== 'awaiting_approval') { clearInterval(approvalPoll); approvalPoll = null; }  // ended elsewhere
  } catch (e) { /* asked again on the next tick */ } finally {
    busy = false;
    if (queued) { const q = queued; queued = null; turn(...q); }
  }
}

// ---- requests ----
async function post(url, body) {
  const raw = body instanceof Blob;  // a photo goes as the raw body; the server checks its bytes
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': raw ? (body.type || 'application/octet-stream') : 'application/json' },
    body: raw ? body : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Something went wrong. Please try again.');
  return j;
}

async function turn(url, body, youText) {
  if (busy) { queued = [url, body, youText]; return; }  // e.g. Escape pressed while a reply is on its way
  busy = true; earcon.heard();
  const slow = setTimeout(earcon.working, 1000);
  try {
    const r = await post(url, body);
    payStatus(''); $('pay-progress').textContent = '';
    append(youText, r.say, r.lines);
    showItem(r.focus); showPayPal(r.paypal);
    setState(r.state, r.due_in, r.pay, r.say);
    if (r.action === 'link') location.assign('/link/start');
    if (r.action === 'photo') $('package-photo').focus();
  } catch (e) {
    earcon.error(); append(youText, e.message);
  } finally {
    clearTimeout(slow); busy = false;
    if (queued) { const q = queued; queued = null; turn(...q); }
  }
}

const send = (text) => turn('/api/turn', { text }, text);

$('ask').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = msg.value.trim();
  if (!text) { append(null, 'Type a request first, or say help.'); return; }  // never a silent no-op
  msg.value = '';
  // a double Enter: the same text again while it is on its way, or within a second, gets no second reply
  if (text === lastSent.text && (busy || Date.now() - lastSent.at < 1000)) return;
  lastSent = { text, at: Date.now() };
  // anything PIN-like (only digits, spaces, dashes; 4+ digits) is never echoed or announced, in any state
  const hide = /^[\d\s-]+$/.test(text) && text.replace(/\D/g, '').length >= 4;
  turn('/api/turn', { text }, hide ? '(number hidden)' : text);
});

$('package-photo').addEventListener('change', (e) => {
  const f = e.target.files[0];
  e.target.value = '';  // the same photo can be sent again
  if (f) turn('/api/package', f, 'Package photo: ' + f.name);
});

pinForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const pin = pinInput.value.trim();
  pinInput.value = '';
  turn('/api/pin', { pin }, 'PIN entered');
});
$('pin-cancel').addEventListener('click', () => send('cancel'));
$('undo-btn').addEventListener('click', () => send('undo'));

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
    // one press: stops the voice and listening AND acts on a waiting payment, so "press Escape" is always true
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (rec) rec.abort();
    if (state === 'undo_window' && paying) payStatus('Too late to undo: PayPal is taking the payment now.');
    else if (state === 'undo_window') { progress('Undoing the payment.'); send('undo'); }
    else if (HOLD.includes(state)) { progress('Cancelling the payment.'); send('cancel'); }
  }
});

// ---- setup and settings ----
function fillSettings(s) {
  setMode(s.output_mode);
  setState(s.state, s.due_in, s.pay);
  $('setup').hidden = s.onboarded;
  const f = $('settings-form');
  f.output_mode.value = s.output_mode;
  const p = s.prefs;
  f.verbosity.value = p.verbosity; f.simple_mode.checked = p.simple; f.large_text.checked = p.large_text;
  f.default_size.value = p.size; f.avoid_allergens.value = p.avoid.join(', ');
  const c = s.contact || { name: '', email: '', threshold: '' };
  f.contact_name.value = c.name; f.contact_email.value = c.email; f.approval_threshold.value = c.threshold;
  f.scam_hold.checked = c.scam_hold === true;  // off by default: the shopper turns it on
  document.documentElement.classList.toggle('large', p.large_text);
  f.per_order_cap.value = s.per_order_cap; f.daily_cap.value = s.daily_cap;
  showPayPal(s.paypal);
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
    daily_cap: f.daily_cap.value || null, new_pin: f.new_pin.value || null, current_pin: f.current_pin.value || null,
    verbosity: f.verbosity.value || null, simple_mode: f.simple_mode.checked, large_text: f.large_text.checked,
    default_size: f.default_size.value, avoid_allergens: f.avoid_allergens.value,
    contact_name: f.contact_name.value, contact_email: f.contact_email.value, approval_threshold: f.approval_threshold.value,
    scam_hold: f.scam_hold.checked };
  try {
    const s = await post('/api/settings', body);
    f.new_pin.value = ''; f.current_pin.value = '';
    fillSettings(s); status.textContent = s.saved;  // only what changed; "settings" in chat reads the full summary
  } catch (err) {
    status.textContent = 'Error: ' + err.message;
    f.current_pin.value = '';  // a stale value would block retyping (maxlength 4)
    (/new PIN/.test(err.message) ? f.new_pin : f.current_pin).focus();
  }
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});  // installable (PWA)

(async function init() {
  const s = await fetch('/api/settings').then((r) => r.json());
  fillSettings(s);
  const link = new URLSearchParams(location.search).get('link');
  if (link) history.replaceState(null, '', '/');
  const linkMsg = { done: 'PayPal is linked. You can now check out.', cancelled: 'PayPal linking was cancelled. Nothing changed.',
    error: 'PayPal linking did not work. Please try Link PayPal again.' }[link];
  // a payment still pending on the server is always said first after a reload (resume comes from server data)
  append(null, (linkMsg ? linkMsg + ' ' : '') + (s.resume || (s.onboarded ? 'Welcome back. What would you like to shop for?'
    : 'Welcome to Sightline. Please answer the Setup questions first, or start by typing what you want.')),
    s.resume_lines || []);  // e.g. the approval link, still there after a reload
  if (s.onboarded && state !== 'awaiting_pin') msg.focus();  // awaiting_pin: setState already focused the PIN box
})();
