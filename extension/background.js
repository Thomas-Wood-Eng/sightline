// Opt-in sites: when the shopper grants a host in the popup, run the checkout guard there; when they remove it, stop.
const JS = ['detect.js', 'content.js'];

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') chrome.runtime.openOptionsPage(); // first run: set a PIN
});

chrome.permissions.onAdded.addListener(async ({ origins = [] }) => {
  if (!origins.length) return;
  await chrome.scripting
    .registerContentScripts(origins.map((o) => ({ id: o, matches: [o], js: JS, runAt: 'document_start' })))
    .catch(() => {}); // already registered
  for (const tab of await chrome.tabs.query({ url: origins }))
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: JS }).catch(() => {});
});

chrome.permissions.onRemoved.addListener(({ origins = [] }) => {
  if (origins.length) chrome.scripting.unregisterContentScripts({ ids: origins }).catch(() => {});
});
