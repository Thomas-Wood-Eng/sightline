# Bulk: group-buy with all-or-nothing escrow (research, 2026-10-27)

## 1. PayPal feasibility: works, with one design constraint
- **Flow:** create order `intent=AUTHORIZE` -> buyer approves -> `POST /v2/checkout/orders/{id}/authorize` returns an authorization ID. Later: `POST /v2/payments/authorizations/{auth_id}/capture` (optional `amount`, `final_capture`, so partial and multiple captures are allowed) or `/void`. Void needs the auth ID, not the order ID. [Payments v2](https://developer.paypal.com/docs/api/payments/v2/), [capture_request](https://developer.paypal.com/api/payments/v2/definitions/capture_request), [void](https://docs.paypal.ai/payments/methods/paypal/void-an-authorization)
- **Windows:** funds are honoured for **3 days**. The authorization stays **valid 29 days** (US docs also say "valid for 3 days" in the US). [Authorization guide](https://developer.paypal.com/docs/checkout/standard/customize/authorization/), [Extend authorization](https://developer.paypal.com/checkout/extend-authorization.md)
- **Reauthorize:** only on days 4-29, each one gives a new auth ID and a fresh 3-day honour period, up to 115% of the original amount (max +$75). **The docs conflict on how many times:** "multiple" ([guide](https://developer.paypal.com/docs/checkout/standard/customize/authorization/)) vs "a single time" ([extend](https://developer.paypal.com/checkout/extend-authorization.md)). Plan for one.
- **Many buyers -> one merchant:** trivial. Each member's share is its own order to one sandbox business account (the organiser or the Bulk platform). Paying the supplier can use Payouts, or the organiser just pays them; leave it out of the MVP.
- **Sandbox:** there is no way to fast-forward time, so you cannot demo the honour or expiry rules for real. Authorize, capture and void all work right away with sandbox personal accounts. To show a failed capture, use negative testing (`PayPal-Mock-Response` header, see [sandbox negative testing](https://developer.paypal.com/tools/sandbox/negative-testing/)).
- **Alternative for longer campaigns:** vault the payer's PayPal wallet (Vault v3 setup token -> payment token), then charge with `vault_id` only when the campaign succeeds. In sandbox you have to tick the Vault option. Live use needs approval for reference transactions. [Save without purchase](https://developer.paypal.com/docs/checkout/save-payment-methods/purchase-later/payment-tokens-api/paypal/)
- **Agent Toolkit / MCP:** has `create_order`, `get_order`, `pay_order` ("capture payment for an authorized order") and refunds. It has **no authorize-ID capture, void or reauthorize** tools. [Agent tools catalog](https://developer.paypal.com/ai-tools/agent-tools/), [agent-toolkit](https://github.com/paypal/agent-toolkit). Write the escrow tools yourself as thin REST wrappers exposed to the LLM, which is a plus for judges ("we extended the toolkit").

**Recommended design:** campaigns default to **≤72 h** so every authorization sits inside the guaranteed window. The default path is authorize at join, then on threshold capture each auth with `final_capture=true`; on deadline, void all.
- **Campaigns of 4-7 days (opt-in):** at threshold, capture anyway, since auths are valid to day 29 and success is likely but not guaranteed. On a capture failure, reauthorize once. If that also fails, email the member a fresh pay link and hold the supplier order until the shortfall is covered or a backup member takes the slot.
- **Every campaign:** keep a 5-10% overshoot buffer on the threshold.
- **Vault is the "v2" upgrade path.** Don't build it in 5 days.

## 2. Real problem evidence
- **Mechanical keyboard group buys:** pay upfront and wait months. Team Redline collapsed with an estimated ~$100K lost by "hundreds" of buyers ([Keebtalk horror stories](https://www.keebtalk.com/t/group-buy-horror-stories/13831)). A GeekHack GB organiser vanished with funds, and PayPal buyer protection failed because "too much time passed" ([Deskthority](https://deskthority.net/viewtopic.php?p=55177)). The r/MK wiki claims ~10% of GBs never deliver (unverified) ([wiki](https://lr.us.psf.lt/r/MechanicalKeyboards/wiki/psagroupbuys)).
- **Food buying clubs:** a volunteer "treasurer" takes payments and consolidates orders by hand ([Sustain toolkit](https://www.sustainweb.org/foodcoopstoolkit/buyingclubs/), [Goodness FAQ](https://goodness.com.au/buying-groups-faqs/), [Hunger Center toolkit](https://www.hungercenter.org/publications/bulk-buying-club-toolkit-a-guide-to-starting-a-neighborhood-bulk-buying-club/)).
- **Electronics:** parts with high minimum order quantities (MOQs) are pooled through GroupGets: "Nobody will be charged if the campaign does not succeed" ([GroupGets](https://archive.groupgets.com/blog/posts/33-hacking-minimum-orders-for-fun-profit)).
- **The pattern:** organisers collect upfront by Venmo or e-transfer into a spreadsheet. Members carry all the risk, and refunds after a failed buy are manual.

## 3. Competitors and gap
- **Drop (Massdrop):** tiered price drops, charged at the end. **Shut down March 2026** by Corsair, which leaves an open community gap and a good pitch hook ([Wikipedia](https://en.wikipedia.org/wiki/Drop_(company)), [Prism News](https://www.prismnews.com/hobbies/mechanical-keyboards/drop-stops-taking-orders-march-25-as-corsair-consolidates-store)). See also [Massdrop explainer](https://www.pcsteps.com/19102-what-is-massdrop/).
- **Tilt/Crowdtilt:** all-or-nothing group pooling, acqui-hired by Airbnb and closed in 2017 ([Wikipedia](https://en.wikipedia.org/wiki/Tilt.com)).
- **Kickstarter:** all-or-nothing, but for creators, not ad-hoc buyer groups. GroupGets is curated electronics only.
- **Hackathon field:** `repos.json` has one generic "AI crowdfunder" and no threshold group-buy. Devpost search found none ([Groupify](https://gitea.com/abass03cam/groupify-web) and [group-buy-organizer](https://www.pypi.org/project/group-buy-organizer/) are non-PayPal side projects).
- **What makes Bulk different:** any group can start a buy in minutes, with real authorize-then-capture-or-void escrow and an AI organiser instead of a curated catalog.

## 4. Where the AI genuinely helps
1. **Price sheet to tiers:** parse a PDF, image or pasted price list into structured tiers (MOQ, unit price, shipping), and ask about anything ambiguous.
2. **Shares:** compute each member's share, including pro-rata shipping and tax, and recompute when tiers unlock ("3 more units drops everyone to $X").
3. **Member Q&A agent:** grounded in the campaign ("when am I charged?", "what if it fails?").
4. **Threshold nudges:** draft share messages and pick the best close time.
5. **Supplier outreach:** draft a quote-request or negotiation email.
6. **Exceptions:** a capture fails and the agent proposes the fix (reauth, pay link, backup member) for the organiser to approve. This human-in-the-loop step is also the guardrail story.

## 5. Demo (≤3 min) and MVP (5-6 days)
- **Demo script:**
  - 0:00 Hook: the Redline loss and Drop's closure.
  - 0:20 Organiser pastes a coffee or filament price sheet. The agent builds the tiers and the campaign page.
  - 0:50 Three sandbox buyers join and approve PayPal. The AG Grid shows rows going "Authorized".
  - 1:30 A tier unlocks and the shares recompute live.
  - 1:50 Threshold hit, the agent captures all and rows turn green.
  - 2:15 Second campaign: the deadline passes and all rows are voided.
  - 2:35 Mock-declined capture and the agent's fix.
  - 2:50 Close.
- **MVP:** Next.js + PayPal JS SDK; server routes for create/authorize/capture/void; SQLite; Claude with tool-use (parse_sheet, quote_shares, capture_all, void_all, draft_message); AG Grid community; a cron/"run deadline now" button.
  - Day 1 payments.
  - Day 2 grid and campaign model.
  - Day 3 agent.
  - Day 4 exceptions and polish.
  - Day 5 video.
- **Skip:** Payouts, Vault, auth.
- **Risks:**
  - Ambiguous honour-window docs: mitigate with ≤72 h defaults and say so on screen.
  - Live legality of holding pooled funds (money transmission): pitch the organiser as the merchant of record.
  - Sandbox popups slow the demo: pre-record the approvals.
  - "Just Kickstarter": lead with the AI price sheet and tier engine.

## 6. Verdict
**Novelty 8, Feasibility 8, Impact 6, Demo-ability 9.** Nobody visible is building threshold group-buys. The obvious incumbents (Drop, Tilt) are dead, and authorize/capture/void across many payers uses Orders v2 more deeply than the crowded "NL to checkout" entries. Feasibility is high because every call works in sandbox. The only real constraint is the 3-day honour window, which a ≤72 h campaign default turns into a feature ("decide fast"). The missing toolkit tools are easy to wrap. Impact is real but niche (clubs, co-ops, hobby GBs), so the pitch must make the trust and escrow story hit hard. The demo has a natural climax (grid turns green on capture, grey on void), which suits Best Use of Agentic Commerce and the AG Grid prize.
