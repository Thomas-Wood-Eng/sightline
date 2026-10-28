// Shared by the popup and the dialog. Stores only a salted SHA-256 of the PIN, never the PIN itself.
globalThis.SightlinePin = (() => {
  const store = chrome.storage.local;
  const MAX_TRIES = 3;
  const LOCK_MS = 5 * 60 * 1000;
  const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
  const hash = async (pin, salt) => hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${salt}:${pin}`)));

  async function state() {
    const s = await store.get({ pinHash: '', pinSalt: '', fails: 0, lockUntil: 0 });
    return { ...s, noPin: !s.pinHash, locked: s.lockUntil > Date.now(), until: s.lockUntil };
  }

  async function set(pin) {
    const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
    await store.set({ pinSalt: salt, pinHash: await hash(pin, salt), fails: 0, lockUntil: 0 });
  }

  // { ok } | { left } | { locked, until } | { noPin }
  async function check(pin) {
    const s = await state();
    if (s.noPin || s.locked) return s;
    if ((await hash(pin, s.pinSalt)) === s.pinHash) {
      await store.set({ fails: 0 });
      return { ok: true };
    }
    const fails = s.fails + 1;
    if (fails >= MAX_TRIES) {
      const until = Date.now() + LOCK_MS;
      await store.set({ fails: 0, lockUntil: until });
      return { locked: true, until };
    }
    await store.set({ fails });
    return { left: MAX_TRIES - fails };
  }

  const lockedText = (until) =>
    `Too many wrong PINs. Sightline is locked until ${new Date(until).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}. Nothing was paid.`;

  return { state, set, check, lockedText };
})();
