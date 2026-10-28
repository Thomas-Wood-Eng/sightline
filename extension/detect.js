// Sightline page heuristics. Plain words, roles and visible text only, never class names (those change every release).
globalThis.SightlineDetect = (() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const CLICKABLE = 'button, input[type=submit], input[type=button], input[type=image], [role=button], a[href]';

  // The final "money moves now" buttons. Anchored, so "Pay with PayPal" or "Continue to payment" do not match.
  const PAY = /^(pay|pay now|pay (?=[^a-z]*\d)[^a-z]{1,16}( ?[a-z]{3})?|complete (your )?(purchase|order|payment)|place (your )?order|agree (and|&) (continue|pay)|confirm (and pay|order|purchase|payment)|buy now|submit (order|payment))$/i;

  const CODES = 'USD|EUR|GBP|CAD|AUD';
  // "$45.67", "US$45.67", "$ 49 .19" (amount split across spans), "45.67 USD", "45,67 €".
  const AMOUNT = new RegExp(
    `(?:(?:US|C|A|NZ)?\\$|[€£¥]|\\b(?:${CODES}) ?)\\s*(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\s*\\.\\s*\\d{2})?(?: ?(?:${CODES})\\b)?` +
    `|\\b\\d+(?:[.,]\\d{3})*[.,]\\d{2} ?(?:[€£]|(?:${CODES})\\b)`);
  const TOTAL = /(?<!sub[- ]?)\b(order total|grand total|total due|amount due|total to pay|you pay|total)\b(?! ?(savings|saved|discount|before))/i;
  const PAYEE_INLINE = /\b(?:cancel and return to|you(?:'|’)?re paying|you are paying|pay to|payment to|payee|merchant|seller|sold by|sold and shipped by|shipped and sold by)\s*:?\s+(.+)$/i;
  const PAYEE_LABEL = /^(?:payee|merchant|seller|sold by|pay to)\s*:?$/i;
  const SCAMS = [
    [/gift ?cards?/i, 'gift cards'],
    [/wire transfer|western union|moneygram/i, 'wire transfers'],
    [/crypto|bitcoin|\bbtc\b|\busdt\b|ethereum/i, 'cryptocurrency'],
  ];

  const clean = (s) => norm(s).replace(/([$€£¥.]) /g, '$1').replace(/ \./g, '.');
  const value = (s) => {
    const d = s.replace(/[^\d.,]/g, '');
    return parseFloat(/,\d{2}$/.test(d) ? d.replace(/\./g, '').replace(',', '.') : d.replace(/,/g, ''));
  };
  const buttonText = (el) =>
    norm(el.getAttribute('aria-label') || (el.tagName === 'INPUT' ? el.value || el.alt : el.innerText) || el.title);
  const isPayButton = (el) =>
    !el.disabled && el.getAttribute('aria-disabled') !== 'true' &&
    PAY.test(buttonText(el).replace(/^[^\p{L}\p{N}$€£]+|[^\p{L}\p{N}$€£]+$/gu, ''));

  // Rendered lines: a label and its amount usually sit on one line or the next few, whatever the markup.
  const lines = (doc) => doc.body.innerText.split('\n').map(norm).filter(Boolean);

  function findTotal(ls) {
    let best = null;
    ls.forEach((line, i) => {
      const m = TOTAL.exec(line);
      const a = m && AMOUNT.exec([line.slice(m.index), ...ls.slice(i + 1, i + 4)].join(' '));
      if (!a) return;
      const rank = m[1].toLowerCase() === 'total' ? 1 : 2; // "Order total" beats a bare "Total"; later beats earlier
      if (!best || rank >= best.rank) best = { amount: clean(a[0]), rank };
    });
    return best ? best.amount : '';
  }

  function findPayee(ls) {
    for (let i = 0; i < ls.length; i++) {
      const raw = PAYEE_LABEL.test(ls[i]) ? ls[i + 1] : PAYEE_INLINE.exec(ls[i])?.[1];
      const name = norm(raw).replace(/[.,;:!]+$/, '');
      if (name.length >= 2 && name.length <= 60 && !AMOUNT.test(name)) return name;
    }
    return '';
  }

  const findScams = (text) => SCAMS.filter(([re]) => re.test(text)).map(([, label]) => label);

  // Everything the Readback needs, as plain sentences.
  function analyze(button, doc = document) {
    const ls = lines(doc);
    const label = buttonText(button);
    const onButton = AMOUNT.exec(label);
    const total = findTotal(ls);
    const amount = onButton ? clean(onButton[0]) : total;
    const payee = findPayee(ls) || norm(doc.querySelector('meta[property="og:site_name"]')?.content);
    const host = doc.location.hostname;
    const notices = [];
    if (!amount) notices.push('Sightline could not find the total on this page. Check it before paying.');
    if (onButton && total && value(amount) !== value(total))
      notices.push(`The button says ${amount} but the page total says ${total}. Check it before paying.`);
    if (!payee) notices.push(`Sightline could not find who you are paying. This page is ${host}.`);
    const scams = findScams(ls.join(' '));
    if (scams.length)
      notices.push(`Warning: this page mentions ${scams.join(' and ')}. Real shops rarely ask for these; scammers often do.`);
    const main = `You are about to pay ${amount || 'an amount Sightline could not read'} ${payee ? 'to ' + payee : 'on ' + host}.`;
    return { main, notices, button: label, amount, payee };
  }

  return { CLICKABLE, isPayButton, buttonText, findTotal, findPayee, findScams, analyze, AMOUNT };
})();
