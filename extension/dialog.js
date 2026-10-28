// The Readback dialog: review -> Confirm -> PIN -> 10-second undo window -> tell the page script to press pay.
const UNDO_SECONDS = 10;
const $ = (id) => document.getElementById(id);
const info = JSON.parse(decodeURIComponent(location.hash.slice(1)));
const post = (msg) => parent.postMessage(msg, '*'); // carries no secrets: page text, "cancel" or "pay"
// Speech goes through the page's content script: this frame has no user activation yet, so it may not speak on its own.
const say = (text, live = false) => {
  if (live) $('status').textContent = text;
  post({ sightline: 'say', text });
};

let timer = null;
const cancel = () => { clearInterval(timer); post({ sightline: 'cancel' }); };

let focusTarget = null;
function show(step, focusEl) {
  for (const s of ['review', 'pin', 'undo']) $('step-' + s).hidden = s !== step;
  (focusTarget = focusEl).focus();
}
// The page focuses this frame after it loads; land on the current step's control, not the frame's body.
addEventListener('focus', () => { if (document.activeElement === document.body) focusTarget?.focus(); });

function stop(text) { // no PIN set, or locked: the only way out is Cancel
  $('pin-row').hidden = $('pin-submit').hidden = true;
  $('pin-msg').textContent = text;
  show('pin', $('step-pin').querySelector('.cancel'));
  say(text);
}

$('readback').textContent = info.main;
for (const n of info.notices) $('notices').append(Object.assign(document.createElement('li'), { textContent: n }));
$('button-label').textContent = info.button;
show('review', $('confirm'));
say([info.main, ...info.notices, 'Press Confirm to continue, or Escape to cancel.'].join(' '));

$('confirm').onclick = async () => {
  const s = await SightlinePin.state();
  if (s.noPin) return stop('You have not set a Sightline PIN yet. Open the Sightline extension, set a PIN, then try again. Nothing was paid.');
  if (s.locked) return stop(SightlinePin.lockedText(s.until));
  show('pin', $('pin'));
  say('Type your PIN, then press Enter.');
};

$('step-pin').onsubmit = async (e) => {
  e.preventDefault();
  const r = await SightlinePin.check($('pin').value);
  $('pin').value = '';
  if (r.ok) return startUndo();
  if (r.locked) return stop(SightlinePin.lockedText(r.until));
  if (r.noPin) return stop('No Sightline PIN is set. Nothing was paid.');
  const text = `Wrong PIN. ${r.left} ${r.left === 1 ? 'try' : 'tries'} left.`;
  $('pin-msg').textContent = text;
  say(text);
  $('pin').focus();
};

function startUndo() {
  let left = UNDO_SECONDS;
  const tick = () => ($('count').textContent = `Paying in ${left} second${left === 1 ? '' : 's'}. Press Undo or Escape to stop.`);
  tick();
  show('undo', $('undo'));
  say(`PIN correct. Paying in ${UNDO_SECONDS} seconds. Press Undo or Escape to stop.`, true);
  timer = setInterval(() => {
    left -= 1;
    if (left <= 0) { clearInterval(timer); post({ sightline: 'pay' }); return; }
    tick();
    if (left === 5) say('5 seconds.', true);
  }, 1000);
}

$('undo').onclick = cancel;
for (const b of document.querySelectorAll('.cancel')) b.onclick = cancel;

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.preventDefault(); cancel(); return; }
  if (e.key !== 'Tab') return;
  // Focus trap: wrap Tab inside the dialog instead of escaping to the (inert) page or the browser.
  const items = [...$('dialog').querySelectorAll('button, input')].filter((el) => el.offsetParent !== null);
  const i = items.indexOf(document.activeElement);
  const next = e.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : (i === items.length - 1 ? 0 : i + 1);
  e.preventDefault();
  items[next]?.focus();
});
