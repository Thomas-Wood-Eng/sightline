// Popup and options page: on/off, this site, PIN, speech.
const $ = (id) => document.getElementById(id);
const store = chrome.storage.local;
const say = (text, focusEl) => {
  $('status').textContent = text;
  focusEl?.focus();
};

(async () => {
  const s = await store.get({ enabled: true, speak: true, rate: 1, pinHash: '' });
  $('enabled').checked = s.enabled;
  $('speak').checked = s.speak;
  $('rate').value = String(s.rate);
  $('current-row').hidden = !s.pinHash;
  if (!s.pinHash) say('Set a PIN to start. Sightline cannot confirm payments without one.');

  for (const id of ['enabled', 'speak']) $(id).onchange = () => store.set({ [id]: $(id).checked }).then(() => say('Saved.'));
  $('rate').onchange = () => store.set({ rate: Number($('rate').value) }).then(() => say('Saved.'));

  // Opt-in per site: Chrome asks the shopper for this one host; background.js then registers the content script there.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let url = null;
  try { url = new URL(tab.url); } catch {}
  if (!url || !/^https?:$/.test(url.protocol)) return;
  $('site').hidden = false;
  $('site-name').textContent = url.hostname;
  if (/^www\.(sandbox\.)?paypal\.com$/.test(url.hostname)) {
    $('site-paypal').hidden = false;
    $('site-row').hidden = true;
    return;
  }
  const origins = [`${url.protocol}//${url.hostname}/*`];
  $('site-on').checked = await chrome.permissions.contains({ origins });
  $('site-on').onchange = async () => {
    const on = $('site-on').checked;
    const done = on ? await chrome.permissions.request({ origins }) : await chrome.permissions.remove({ origins });
    if (!done) $('site-on').checked = !on;
    say(!done ? 'Not changed.' : on ? 'On for this site.' : 'Off for this site. Reload the page to finish turning it off.');
  };
})();

$('pin-form').onsubmit = async (e) => {
  e.preventDefault();
  const pin = $('new').value;
  if (!/^\d{4,8}$/.test(pin)) return say('The new PIN must be 4 to 8 digits.', $('new'));
  if (pin !== $('repeat').value) return say('The two new PINs do not match.', $('repeat'));
  if (!$('current-row').hidden) {
    const r = await SightlinePin.check($('current').value);
    if (!r.ok) return say(r.locked ? SightlinePin.lockedText(r.until) : 'The current PIN is wrong.', $('current'));
  }
  await SightlinePin.set(pin);
  e.target.reset();
  $('current-row').hidden = false;
  say('PIN saved.');
};
