# Sightline: project proposal (for approval)

PayPal AI Hackathon (Devpost). Submission deadline **Thu 2026-11-12, 12:00 PT**. Judging Dec 1-15; winners around Dec 21.
Research: `research_sightline.md` (problem), `research_tech.md` (stack), `research_ux.md` (UX, testing, video),
`IDEAS.md` (landscape: 182 public competitor repos, none on accessibility). Day-1 test: `spike_paypal.py`.

---

## 1. The pitch
Blind and low-vision shoppers can often *find* a product online, then lose it at checkout to CAPTCHAs, popups and unlabelled buttons.
Even PayPal's own checkout popup failed a 2025 keyboard and labelling audit.

**Sightline** is a voice- and keyboard-first shopping agent that takes the user from "find me a warm hoodie under $40" to a paid order
without touching a single inaccessible widget. It describes products honestly, separating "listing says" from "photo suggests".
It never invents a number. Before any money moves, it reads back every dollar **from PayPal's own order data** (we call this step
the *Readback*), then waits for an explicit "confirm" and a typed PIN. **The agent does the clicking; the user makes every decision.**

## 2. Why it can win (the 5 equally weighted judging criteria)
| Criterion | Our angle |
|---|---|
| Technical implementation | Save PayPal once (Vault v3), then hold → read back → capture or release (Orders v2 AUTHORIZE / capture / void), idempotency keys, Agent Toolkit for read-only order tools, a three-lane speed architecture |
| Design | A complete product: onboarding, linking, browse, describe, compare, cart, checkout, cancel, receipt. Fully usable with a screen reader and keyboard (WCAG 2.2) |
| Potential impact | 2.2B people with a vision impairment (WHO). CAPTCHA is the #1 barrier for screen-reader users (WebAIM, 1,539 respondents). About 5,000 US accessibility lawsuits in 2025, ~70% against online stores. EU Accessibility Act in force since June 2025 |
| Innovation | No visible competitor among 182 entries. Safety-first agentic payments: "the agent proposes, PayPal's numbers are read back, the human confirms" |
| Presentation | The video opens on a black screen with a screen reader talking; a real blind tester completes a purchase |

Prizes we target: Most Impactful ($5K), Best Use of Agentic Commerce or Best Use of PayPal + AI ($5K), and the grand prizes ($12K / $8K / $5K).
A project can win one main or special prize plus one sponsor prize. Possible sponsor prize: APIMatic, if using PayPal's
APIMatic-generated Python SDK counts (terms to check).

## 3. What the user experiences (MVP)
1. **Onboarding, once:** "Are you using a screen reader?" sets how replies are spoken. Choose a 4-digit PIN and a per-order and daily spending cap.
2. **Link PayPal, once:** a normal full-page PayPal login (no popup), which screen readers handle well.
   We say up front: "PayPal's login is your security boundary; we never see your password."
3. **Shop by voice or typing.** A push-to-talk button (Alt+Shift+M) and a text box, both always available.
   - Search gives **at most 3 items**: name, price, rating, in 15 words or fewer each.
   - "Describe it": what it is, size, exact colour, material and texture, condition, what's in the box, allergens.
     Every fact is labelled "listing says" or "photo suggests (unverified)"; unknowns are "not stated".
   - "Compare them" goes one attribute at a time ("Cheapest: B. Best rated: A").
   - "Repeat", "more", "spell that", "that's wrong" and Esc work at any time.
4. **Checkout:** "check out" puts the money on hold at PayPal. Then the Readback, in a fixed order: item, quantity, price, shipping, tax,
   **total**, delivery date, seller, all taken from PayPal's response. Then the user says or types "confirm", types the PIN, the payment is
   taken, and a receipt is read out. "Cancel" releases the hold. Over the cap, the purchase is refused and the cap and overage are stated.
   Nothing ever times out.
5. **Sandbox only:** fake money and a fake 40-product shop with properly licensed photos.

Not included: real merchants, other payment methods, mobile apps, other languages, voice input on Firefox (it uses the text box).

## 4. How it works: three lanes for speed
Goal: **most turns are instant, the rest start speaking in about 1 second, and no number ever comes from an AI.**

- **Lane 0, no AI, under 300 ms.** A command parser handles the many fixed phrases ("next", "repeat", "add it", "what's in my cart",
  "cancel", "confirm", numbers, yes and no). The **whole checkout** runs here too (Readback → confirm → PIN → charge or release),
  so the money step is both instant and deterministic.
- **Lane 1, Gemini Flash-Lite, about 1 s.** For free-form requests ("something warm for winter under $40", "which is softer?").
  It calls our tools: a local product search, product facts, prepared Q&As, prepared comparisons, cart actions. It never sees prices,
  only bands like "under $50". Every amount the user hears is filled in by our server from the catalogue or PayPal's data, and a
  guard blocks any money figure in the AI's text. Each call has a 4 s timeout and one retry, then a fallback menu.
  Day-1 timing: `gemini-flash-lite-latest` median **0.87 s**; fallback `gemini-3.5-flash-lite` 1.43 s.
- **Lane 2, Gemini Pro with vision, offline.** Before launch it does the heavy thinking once per product: an accessible description
  from the photo, structured facts, "listing says" vs "photo suggests", about 10 likely questions with answers, and comparisons with
  similar items. I review all of it by hand. Lane 1 looks these up instead of reasoning live, which is why it can be both fast and good.
  Rare hard questions are escalated to Gemini Pro live, with "checking, one moment".
- **Hiding delay:** a short sound under 100 ms on every input ("heard you"), an "on it" cue past 1 s, prefetching the next item's details.
  Replies go into the page **complete**, not word by word, so the screen reader reads them once.
- **Voice:** push-to-talk with the browser's free speech recognition (Chrome and Edge), with typing as an equal option. Replies are read
  by the user's **own screen reader**, or by an optional built-in voice for low-vision users without one, never both at once.
- **PayPal:** all money calls are in our own code, never an AI tool:
  link (`/v3/vault/setup-tokens` → PayPal login → `/v3/vault/payment-tokens`), hold (`/v2/checkout/orders`, intent AUTHORIZE, saved wallet),
  charge (`/authorizations/{id}/capture`), release (`/void`). Every checkout attempt gets one idempotency key, so a repeated
  "confirm" can never charge twice. PayPal's Agent Toolkit supplies read-only "where's my order?" tools.
- **Stack:** Python, FastAPI, Gemini SDK, plain HTML and JavaScript (simplest for accessibility). No database: state lives in a signed cookie.
  All AI calls go through one file (`llm.py`), so switching to Claude later is one file.

## 5. Safety rules (non-negotiable)
- The agent never buys on its own. Every purchase needs the Readback, "confirm" and a **typed** PIN; a spoken PIN can be overheard.
- Spending caps can only be changed in Settings, never mid-conversation, which guards against coercion and prompt injection.
- Never guess size, allergens or price: say "not stated" and offer a next step.
- No photos or transcripts are stored. We say plainly that Chrome's speech recognition sends audio to Google, and typing works just as well.
- Language: "blind and low-vision people". The problem is an inaccessible checkout, not a person. No "inspiring".

## 6. Acceptance bar: 10 testable requirements
1. Every task can be done with NVDA and the keyboard alone, with the screen hidden.
2. NVDA announces each reply exactly once.
3. Results show at most 3 items, 15 words or fewer each.
4. "Repeat", "more", "spell that" and Esc work everywhere.
5. No payment without the full Readback, "confirm" and a typed PIN.
6. Spoken amounts match PayPal's order breakdown exactly, and never come from the AI.
7. A purchase over the cap is refused, stating the cap and the overage.
8. Visual claims are labelled "listing says" or "photo suggests"; unknowns are "not stated".
9. No time limits; shortcuts use modifier keys only; focus stays visible at 400% zoom.
10. Automated checks (axe, Lighthouse) show 0 critical issues, and both blind testers complete "buy one, then cancel one".

## 7. Schedule
| Dates | Milestone | Checkpoint |
|---|---|---|
| ✅ Oct 27 | Day-1 test: PayPal save-once, hold, charge, release, no double charge, all passed. Gemini timing done | Passed, so no fallback plan needed |
| Oct 28 | Draft the tester call; you post it (AppleVis, r/Blind after checking with mods, CNIB, campus disability centre) | — |
| Oct 28-30 | 40-product shop with licensed photos and CREDITS.md; Lane 2 descriptions; my review | — |
| Oct 31-Nov 2 | Lane 0 commands + checkout + PayPal linking, end to end by typing | Checkout works end to end by Nov 2 |
| Nov 3-4 | Lane 1 Gemini agent + price guard; voice, sounds, screen-reader output, built-in voice option | Median reply ≤ 1.5 s |
| Nov 5 | Full NVDA, keyboard-only and zoom pass; automated checks; fixes | 0 critical issues |
| Nov 6-7 | Blind tester sessions (2 × 25 min, volunteers, credited) | Fix the top 3 issues they hit |
| Nov 8-9 | Fixes; deploy to Render (free); README with judge login, demo PIN and cap; open-source licence | — |
| Nov 10 | Record the video: captions, narrated actions, tester clips only with written consent | — |
| Nov 11 | Devpost write-up; final check of the repo, live link and video | — |
| Nov 12 AM | Buffer. **You** submit before 12:00 PT | — |

## 8. Cost: $0
- **AI:** Gemini free tier. Lane 2 for 40 products fits in the free daily limits.
  On the free tier Google may use prompts to improve its products; testers only see the fake shop, and the consent script says so.
- **Hosting:** Render's free tier, with a free uptime monitor pinging every 10 minutes so judges don't wait for it to wake.
  It's within the 750 free hours a month.
- **PayPal sandbox, GitHub, YouTube, browser speech recognition, NVDA:** free. No card on any service.
- **Testers:** volunteers, asked for 25 minutes and credited. Optional: promise them a share if we place, which costs nothing up front.

## 9. What only you can do
- ✅ PayPal sandbox keys and the Gemini key (done; both in `.env`, which is git-ignored).
- Create free accounts: GitHub (public repo) and Render (sign in with GitHub, no card); later an UptimeRobot account.
- Testers: entirely the user's call. Claude does not draft or post any tester call (user decision, 2026-10-27).
- Record the voice-over (I'll write the script), and submit on Devpost.
- Optional: the tester-share promise.

## 10. Risks
1. ✅ **PayPal sandbox behaviour.** Passed on day 1. Gotcha for the README: judges must log in as the *personal* test buyer;
   the business account gets "you are the seller" and breaks that approval link.
2. **Screen reader speaking twice, or flaky speech recognition.** Screen-reader mode by default, typing always available, NVDA tests on Nov 3 and Nov 5.
3. **No blind testers in time.** Post on Oct 28 through four channels. Fallback: an accessibility professional or experienced screen-reader
   user reviews it, and the video says so honestly.
4. **AI misstating a price or a photo detail.** The three-layer price guard; photo claims reviewed by hand and labelled.
5. **Gemini free-tier stalls or rate limits.** Timeout, one retry, a fallback model, and most turns never touch AI (Lane 0).
6. **Name.** "Sightline" overlaps with Sightline Payments, a US payments company. You chose it knowingly; fine for a hackathon.
7. **Scope creep.** The MVP is the 10 requirements; anything else waits until after Nov 9.
