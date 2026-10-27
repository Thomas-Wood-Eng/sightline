# Sightline: research (2026-10-27)

## 1. Is the problem real?
- **Scale:** 43M people are blind and 295M have moderate or severe vision impairment worldwide ([Lancet GH 2021](https://pubmed.ncbi.nlm.nih.gov/33275950/), [WHO](https://who.int/mediacentre/factsheets/fs282/en/)). In the US, 49.5M adults report some difficulty seeing ([AFB](https://www.afb.org/research-and-initiatives/statistics/adults)). In Canada it is about 1.5M ([CNIB](https://www.cnib.ca/en/sight-loss-info/blindness/blindness-canada)).
- **Barriers:** In WebAIM's screen-reader survey (n=1,539), CAPTCHA is "by far" the worst barrier, followed by alt text, complex forms and headings. 91% use a mobile screen reader, and JAWS (40.5%) and NVDA (37.7%) lead on desktop ([WebAIM SR #10](https://webaim.org/projects/screenreadersurvey10/)). 55.5% of the top 1M home pages have images with no alt text ([WebAIM Million 2025](https://webaim.org/projects/million/2025)).
- **Checkout specifically:** Form fields often fail with screen readers and error messages get buried ([SOUPS 2019](https://www.usenix.org/sites/default/files/soups2019posters-napoli.pdf)). Blind users take about 51 seconds per audio CAPTCHA, and PayPal's was among those tested ([study summary](https://a11y-paradise.onrender.com/reviews/69d002dc87d160b6499c6040)). A Nov-2025 audit of the PayPal/Braintree checkout modal found an unlabelled close control, errors shown by colour only and keyboard failures ([WooCommerce ACR](https://woocommerce.com/fr/accessibility/paypal-braintree-for-woocommerce-accessibility-conformance-report/)).
- **Money and law:** 69% of disabled shoppers click away from hard sites, worth £17.1bn a year in the UK ([Click-Away Pound](https://abilitynet.org.uk/news-blogs/research-shows-businesses-lose-17-billion-ignoring-accessibility-needs)). There were more than 5,000 US digital-accessibility suits in 2025, about 70% against e-commerce ([UsableNet via newswire](https://www.newswire.com/news/digital-accessibility-lawsuits-surge-in-2025-22618502)). The EU Accessibility Act has applied to e-commerce and consumer payment services since 28 Jun 2025 ([Osborne Clarke](https://www.osborneclarke.com/insights/eu-accessibility-act-time-start-implementation-projects-now)).

## 2. PayPal: the hard constraint
- PayPal says its site supports JAWS, NVDA and VoiceOver and targets WCAG 2.2 AA ([PayPal accessibility](https://www.paypal.com/ie/accessibility)). Even so, popups and iframes are the weakest point for screen readers (see the audit above).
- **The constraint:** a PayPal order can only be paid after the buyer approves it on PayPal (popup or `approve` redirect link) and logs in. An agent cannot bypass this, and it should not try.
- **Best legitimate design (sandbox):**
  1. **One-time link step.** Create a setup token (`POST /v3/vault/setup-tokens`) and open the `approve` link as a **full-page redirect** (not the JS SDK popup). The buyer approves a billing agreement once with their own screen reader, then the server swaps it for a payment token ([save without purchase](https://developer.paypal.com/api/payment-tokens/save-without-purchase/paypal)).
  2. **Every later purchase is fully voice-driven.** The server runs Orders v2 create+capture with `payment_source.paypal.vault_id` ([save with purchase / vault_id](https://developer.paypal.com/api/orders-v2/save-with-purchase/paypal)). It does this only after a spoken readback of the total and an explicit "confirm" plus a spoken PIN, with a per-order cap.
  3. **Fallback:** if vaulting is not enabled in the sandbox app, run a normal Orders v2 flow with a full-page redirect to approval.
- **Pitch it honestly:** the PayPal login stays the buyer's security boundary, and Sightline removes everything else. That framing reads as responsible "agentic commerce".
- **Agentic context:** PayPal's Agent Toolkit and MCP server ([blog](https://developer.paypal.com/community/blog/paypal-agentic-ai-toolkit/)) and its Agentic Commerce Services, Agent Ready and Store Sync (Oct 2025, [newsroom](https://newsroom.paypal-corp.com/2025-10-28-PayPal-Launches-Agentic-Commerce-Services-to-Power-AI-Driven-Shopping)). Use the Toolkit for order tools so the "PayPal + AI" story is explicit.

## 3. Competitors
- **Be My Eyes / Be My AI** describes photos and since May 2025 includes an InnoSearch shopping portal ([AppleVis](https://applevis.com/comment/189228)). It is the closest rival, but it is not a payment-native agent with safeguards.
- **Aira** offers paid human interpreters, free at Walmart ([Aira](https://aira.io/aira-at-walmart)). **Seeing AI** reads labels but does not shop.
- **Alexa** shopping is voice-first, but voice purchasing is on by default and caused accidental orders (the "dollhouse" case). A 4-digit voice code is opt-in ([Amazon help](https://digprjsurvey.amazon.com/csad/help/node/GAA2RYUEDNT5ZSNK)). Sightline makes confirmation mandatory.
- **Overlays:** the NFB condemned them, 800+ experts signed the Overlay Fact Sheet, and the FTC fined accessiBe $1M in 2025 ([Roselli](https://adrianroselli.com/2025/01/ftc-catches-up-to-accessibe.html)). Sightline must **not** look like an overlay; it is a standalone agent.
- **Hackathon clones:** Kalon and NuC Shop on Devpost ([1](https://devpost.com/software/kalon), [2](https://devpost.com/software/nuc-shop)) and LookLoud.ai ([UW](https://create.uw.edu/create-aiaccessibility-hackfest-winter-24)). None has real payment. None of the 182 repos in `repos.json` touches accessibility or voice.

## 4. Design principles
- **Don't hijack speech.** Write every reply into an `aria-live` region so the user's own screen reader speaks it at their own speed and voice. Offer TTS only as an option.
- **Verbosity levels:** brief, normal and detailed, and "repeat" or "spell that" on demand.
- **Purchases:** never auto-purchase. Before any payment, read back the item, quantity, every fee and the total, and require an explicit yes.
- **Use semantic HTML that works by keyboard alone.** Voice must be optional, because many blind users prefer typing.
- **Admit uncertainty** ("the photo suggests navy, but the listing doesn't say"), since blind users can't verify images ([AppleVis thread](https://applevis.com/comment/146734)).
- **Testing:** run it yourself with NVDA, the screen off and the mouse unplugged, and run axe DevTools. For real testers, ask r/Blind (check its rules), the AppleVis forums, an NFB chapter or the campus disability office. Pay testers: Fable pays about £34/h ([criplife](https://criplife.co.uk/?p=20405)), so a $40 gift card per 30 minutes is fair. Get consent, use sandbox only, and credit testers in the README.

## 5. MVP (5-6 days) and demo
- **Catalog:** DummyJSON products API (real images, prices, ratings) cached into a local JSON demo store. Prices come only from structured data, never from vision.
- **Days:** 1) catalog plus chat agent with tools (search, describe, compare). 2) Vision description of photos. 3) PayPal setup token, vault and order. 4) Confirmation state machine, PIN and cap. 5) NVDA pass and voice input via Web Speech. 6) Video.
- **Video:** 0:00 a blind tester's quote or the stats. 0:20 the screen goes black and the viewer hears NVDA plus Sightline. "Find a waterproof jacket under $80" leads to a comparison of three and a photo description. 1:30 the user adds an item, and the agent reads back the subtotal, shipping and tax total from the PayPal order response. "Confirm", PIN, paid, receipt read aloud. 2:20 the safeguards: a cap breach and a cancelled order. 2:45 the impact and law line.
- **Risks:**
  - *Misstated price:* the LLM never writes numbers. Totals are filled into a template from the `GET /v2/checkout/orders` amount breakdown.
  - *Gimmick perception:* use a real screen reader on camera, with a tester if possible.
  - *Latency:* a streaming text model with short replies, and an "on it" earcon.
  - *Vision hallucination:* separate "listing says" from "photo suggests".

## 6. Verdict
| Novelty | Feasibility | Impact | Demo-ability |
|---|---|---|---|
| 8 | 7 | 9 | 9 |

The field is empty: nothing visible among the 182 repos, and prior hackathon versions lack payments. The pitch lands squarely on "Most Impactful" and "Best Use of Agentic Commerce". Buyer approval is a real constraint, but the vault-once-then-voice design is legitimate, well documented and itself a good story about safe agent payments. Feasibility loses points for sandbox vault enablement, Web Speech quirks and the polish that real accessibility needs. A "screen goes black" video is memorable. The main execution risk is credibility, so one paid blind tester is worth a day of features.
