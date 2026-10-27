# PayPal AI Hackathon: landscape and ideas (2026-10-27)

Due **Thu 2026-11-12, 12:00 PT**. Rules: https://paypalaihackathon.devpost.com/rules. 22,797 registered.
Judging: equal weight on tech implementation, design, impact, innovation and presentation (a video under 3 min).
Prizes: 3 grand prizes, 5 honorable mentions of $5K each (incl. Agentic Commerce, PayPal + AI) + sponsor prizes (AG Grid $5K/$2K/3x$1K).
One project can win at most one grand/HM prize + one sponsor prize.

## What others are already building
Source: public GitHub repos created since 2026-10-01 (`repos.json`, 182 repos, about 99 with real descriptions).
The Devpost gallery stays hidden until judging, so this is only the visible part.

| Theme | Approx. repos | Verdict |
|---|---|---|
| Guardrails, policy gates and spend limits for AI agents that move money (MCP gates, "mandates", firewalls) | 15+ | Saturated |
| Natural-language to PayPal order/invoice, conversational checkout, AI storefront builders | 10+ | Saturated |
| Dispute prevention, mediation and refund shields | 8+ | Saturated |
| Freelancer escrow, milestone payments, evidence-gated release | 7+ | Crowded |
| Invoicing, AR and collections copilots | 6+ | Crowded |
| Booking or appointment agents that take deposits; small-seller copilots | 5+ | Crowded (this kills the earlier "small-seller agent" pitch) |
| Donation/charity transparency, group treasuries, bill splitting | 8+ | Crowded |
| Scam/fraud checks, elder cooling-off wallet | 5 | Some |
| Expense trackers, budgeting | 3 | Some |

Not seen: accessibility/voice-first commerce, threshold group-buying, weather/event-triggered automatic refunds, physical-world vendors.

## Pitches (differentiated)
1. **Group-buy with all-or-nothing escrow ("Bulk").** Neighbours or a student club pool an order to reach a supplier's wholesale minimum.
   The agent negotiates the tiers, collects each share as an authorized-not-captured PayPal order and captures everything once
   the threshold is hit. If the deadline passes it voids all of them. AG Grid tracks who is in.
   Real money saved, a clear agentic-commerce story, and authorize/capture/void is non-trivial use of Orders v2.
2. **Voice-first shopping for blind and low-vision users ("Sightline").** The agent describes products from photos and listings,
   answers questions and confirms totals out loud, then checks out with PayPal and a spoken confirmation step.
   Strongest impact and demo story; nobody visible is doing it. Risk: making the accessibility genuinely good, not a gimmick.
3. **Weather and event-triggered automatic refunds ("Raincheck").** Small outdoor event organisers (markets, tours, kids' camps) set a policy such as
   "refund 100% if rain > 5 mm or the venue cancels". The agent watches forecasts and cancellations and issues PayPal refunds or credits
   per policy, then emails buyers. A novel "parametric refund" angle, and an easy, vivid demo.
4. **Market-stall voice ledger ("Stall").** A farmers' market or street vendor talks to their phone ("sold 3 jars honey to cash, 2 by PayPal").
   AI keeps inventory and sales, generates PayPal QR checkouts on the spot, and does end-of-day reconciliation.
   Concrete underserved audience; Zettle fits the theme. Risk: overlaps "small-seller copilot" in judges' eyes.

## Recommendation
Pitch 1 (Bulk) for the best mix of novelty, tech depth (multi-party authorize/capture/void), agentic commerce and a
clean 3-minute demo. Pitch 3 is the fastest to build. Pitch 2 has the highest impact ceiling but the most execution risk.
