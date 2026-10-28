// Sightline checkout guard: catches the final pay button, shows the Readback + confirm + PIN dialog, then presses it for you.
(() => {
  if (globalThis.__sightlineLoaded) return; // the opt-in path can inject twice into an open tab
  globalThis.__sightlineLoaded = true;

  const D = globalThis.SightlineDetect;
  let settings = { enabled: true, speak: true, rate: 1 };
  chrome.storage.local.get(settings).then((s) => (settings = s));
  chrome.storage.onChanged.addListener((changes) => {
    for (const [k, { newValue }] of Object.entries(changes)) if (k in settings) settings[k] = newValue;
  });

  let gate = null; // the open dialog: { btn, frame, wasInert }
  let bypass = false; // true only while we re-press the button after confirm + PIN + undo window

  const payButton = (e) => {
    const el = e.target instanceof Element ? e.target.closest(D.CLICKABLE) : null;
    return el && D.isPayButton(el) ? el : null;
  };
  const block = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  const active = () => settings.enabled !== false && !bypass;

  function speak(text) {
    if (!settings.speak) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = Number(settings.rate) || 1;
    speechSynthesis.speak(u);
  }

  function open(btn) {
    const info = D.analyze(btn);
    const frame = document.createElement('iframe');
    // The dialog lives in an extension page, so the shop's own scripts cannot read the PIN as it is typed.
    frame.src = chrome.runtime.getURL('dialog.html') + '#' + encodeURIComponent(JSON.stringify(info));
    frame.title = 'Sightline payment check';
    frame.style.cssText =
      'all:initial;position:fixed;inset:0;width:100vw;height:100vh;border:0;margin:0;z-index:2147483647;color-scheme:normal';
    gate = { btn, frame, wasInert: document.body.inert };
    document.body.inert = true; // screen readers and Tab cannot wander into the page behind the dialog
    document.documentElement.append(frame);
    frame.addEventListener('load', () => frame.focus());
  }

  function close(pay) {
    const { btn, frame, wasInert } = gate;
    gate = null;
    document.body.inert = wasInert;
    btn.focus(); // before removing the frame, so the rest of this keystroke lands on the page, not a dead frame
    frame.remove();
    speak(pay ? 'Pressing the pay button now.' : 'Cancelled. Nothing was paid.');
    if (!pay) return;
    bypass = true;
    try { btn.click(); } finally { bypass = false; }
  }

  addEventListener('click', (e) => {
    if (!active()) return;
    const btn = payButton(e);
    if (!btn) return;
    block(e);
    if (!gate) open(btn);
  }, true);

  addEventListener('keydown', (e) => {
    if (!active()) return;
    if (gate && e.key === 'Escape') { block(e); close(false); return; }
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const btn = payButton(e);
    if (!btn) return;
    block(e); // role=button divs act on keydown; native buttons turn Enter into a click we would also catch
    if (!gate && !e.repeat) open(btn);
  }, true);

  addEventListener('keyup', (e) => {
    if (active() && e.key === ' ' && payButton(e)) block(e); // native buttons fire Space clicks on keyup
  }, true);

  addEventListener('message', (e) => {
    // The frame's src uses Chrome's per-session dynamic id, but its messages carry the static extension origin.
    if (!gate || e.source !== gate.frame.contentWindow || e.origin !== `chrome-extension://${chrome.runtime.id}`) return;
    const kind = e.data?.sightline;
    if (kind === 'say') speak(String(e.data.text));
    else if (kind === 'cancel') close(false);
    else if (kind === 'pay') close(true);
  });
})();
