# Sightline: UX and accessibility research (2026-10-27)

Builds on `research_sightline.md`. **Correction to that file:** in WebAIM SR #10 the barrier ranked #2 after CAPTCHA is "interactive elements not behaving as expected". Alt text, forms and headings come 6th to 8th ([WebAIM SR #10](https://webaim.org/projects/screenreadersurvey10/)).

## 1. What blind and low-vision shoppers want (paraphrased)
1. **Three options, short first.** In a CHI 2026 study, 12 blind and low-vision users shopped with a voice agent. Three items at a time was the limit. They wanted name, price and rating first, and details on request ([Shin et al.](https://doi.org/10.1145/3772318.3791681), [summary](https://a11y-paradise.onrender.com/reviews/69e63e5f5570d11947cedf8f)).
2. **"How does it look, is it in style?"** All 12 asked for review summaries and popularity. They also wanted fine colour names ("melange grey"). The visual gaps that matter most are colour, logo, shape and size ([Revamp](https://arxiv.org/abs/2102.00576)).
3. **Confidence is not accuracy.** Vision models sound equally sure when guessing. Blind users called the ability to say "I'm not sure" essential to trust ([ACL 2025 study](https://sciencenews.dk/en/when-ai-sounds-certain-blind-users-have-to-trust-it-even-when-it-is-guessing)). Rich detail makes hallucinations more believable ([Adnin & Das](https://a11y-paradise.onrender.com/reviews/69ae0b021ee16af4bcdca238)).
4. **Payment is where trust is tested.** Users feared handing payment to an agent they can't verify (Shin et al.). Léonie Watson, a blind accessibility expert, calls an agent that won't check out for you "a reasonable limitation for security" ([TetraLogical](https://tetralogical.com/blog/2025/08/08/accessibility-and-the-agentic-web/)). Independence means the user decides and the agent does the clicking.
5. **Voice leaves no trace.** Users asked for double-checks before items went into the cart. Confirm as statements ("Added: navy, M"), not as questions (Shin et al.).
6. **Don't override my screen reader.** The NFB rejects overlays ([Res. 2021-04](https://nfb.org/resources/speeches-and-reports/resolutions/2021-resolutions)). Users tune their own voice and speed.
7. **Photos are private.** Images collected for descriptions shouldn't be stored or misused ([NFB 2024](https://nfb.org/resources/speeches-and-reports/resolutions/2024-resolutions)).
8. **Feedback happens in chat.** Unlabelled thumbs-up/down buttons go unnoticed (Adnin & Das), so make "that's wrong" a command.

The nearest rival is InnoSearch.ai, an accessible shopping portal ([Double Tap](https://doubletaponair.com/innosearch-offers-easier-way-for-blind-people-to-shop/)). It has no published safeguards for the payment step.

## 2. Interaction design
- **W3C guidance** ([NAUR Draft Note](https://www.w3.org/TR/naur/)): repeat on request (REQ 19a), configurable rate (14), simpler-language mode (21c), confirm before irreversible actions (19b), reversibility (25), no time limits (20a).
- **Verbosity:** brief by default. "More", "repeat" and "spell that" work any time, plus brief, normal and detailed settings.
- **Interrupt:** Esc stops speech or cancels a pending action. Typing and push-to-talk are equal options, with no wake word.
- **Money:** numbers come only from data or the PayPal order breakdown. Read in a fixed order: item, quantity, unit price, shipping, tax, **total**, delivery date, seller. Say the currency explicitly.
- **Compare:** at most three items, one attribute at a time ("Cheapest: B. Best rated: A").
- **Describe** in this order: what it is, size, colour, material and texture, condition, what's in the box, then allergens. Split **"Listing says"** from **"Photo suggests (unverified)"**.
- **Screen readers:** put the transcript in `role="log"` (polite) and insert each reply **once it is complete**, because streamed tokens get re-announced. Built-in TTS is **off by default**, set by an onboarding question ("Using a screen reader?"), so nothing is spoken twice.
- **Shortcuts:** modifier combos only. Single-key shortcuts clash with NVDA/JAWS quick keys.
- **Low vision:** layout reflows at 400% zoom, contrast passes, focus is thick and never hidden, and totals use large type.
- **Cognitive load:** one question per turn, plain words, nothing times out.
- **WCAG 2.2 criteria that matter most** ([spec](https://www.w3.org/TR/WCAG22/)):
  - **3.3.4** Error Prevention (financial).
  - **4.1.3** Status Messages.
  - **2.1.1** Keyboard and **2.1.4** Character Key Shortcuts.
  - **2.2.1** Timing Adjustable.
  - **2.4.7** Focus Visible and **2.4.11** Focus Not Obscured.
  - **1.4.3** Contrast, **1.4.10** Reflow and **1.4.11** Non-text Contrast.
  - **3.3.1** Error Identification.
  - **3.3.8** Accessible Authentication: allow paste into the PIN field.
  - **4.1.2** Name, Role, Value.

## 3. Safety, agency, language
- **Safeguards:**
  - The agent never buys on its own initiative. Readback, then an explicit "confirm".
  - The **PIN is typed, not spoken**. Spoken codes, as in Alexa's voice purchasing, can be overheard.
  - A per-order cap and a daily cap, set only in Settings. Caps can't be raised mid-session, and any change triggers an email, which guards against coercion.
  - A cancel window before capture, and an emailed receipt.
- **When unsure:** say so, give one reason and offer a next step. Never guess size, allergens or price.
- **Privacy:** keep no photos or transcripts. Chrome's Web Speech sends audio to Google, so say so and keep typing as an equal option.
- **Language:** the NFB favours "blind" and rejects euphemisms ([NFB](https://nfb.org/node/6361)). CNIB advises avoiding "visually impaired" unless the person chooses it ([CNIB guide](https://cnib.ca/sites/default/files/2024-10/24-0432-CNIB_Inclusive%20Language%20Guidelines_ENG_FINAL-s.pdf)).
  - Use "blind and low-vision people" and ask testers what they prefer.
  - Frame the problem as an **inaccessible checkout**, not a deficient person.
  - Don't say "suffer", "the blind" or "inspiring" ([Stella Young](https://www.ted.com/talks/stella_young_i_m_not_your_inspiration_thank_you_very_much)).

## 4. Testing plan (sighted, solo, Windows)
- **NVDA with Chrome:**
  - Turn on Speech Viewer and Screen Curtain (NVDA+Ctrl+Esc), and unplug the mouse.
  - Learn NVDA+Space, H, NVDA+F7 and Ctrl ([WebAIM guide](https://webaim.org/articles/nvda/)).
- **Narrator** (Ctrl+Win+Enter): one smoke pass. JAWS runs 40-minute sessions in demo mode.
- **Automated:** axe DevTools, Lighthouse and WAVE. They catch only part of the issues.
- **Testers (aim for 2):** pay CAD $50 for 45 min, remote on Zoom with screen and audio shared. For reference, Fable pays £24–34/h ([Crip Life](https://criplife.co.uk/?p=20405)) and a Vancouver study paid $40/h ([Fluid](https://fluidproject.atlassian.net/wiki/x/B82v)). Where to post:
  - AppleVis forums ([precedent](https://applevis.com/forum/ios-ipados/call-beta-testers-conversational-shopping-app)).
  - r/Blind, after checking the rules with the mods.
  - CNIB research (research@cnib.ca).
  - Your campus disability resource centre.
  - Skip Fable: it is enterprise-priced.
- **Consent:**
  > 45-minute test of a student prototype; $50 regardless. We test the software, not you. Payments are fake. May I record audio and use clips in a public demo, credited or anonymous? You can withdraw clips until Nov 10.
- **Tasks:**
  1. Find a gift under $40.
  2. Describe one item.
  3. Compare two items.
  4. Buy one, then cancel one.
- **Questions:**
  1. Where were you unsure what happened?
  2. Was anything too wordy or too terse?
  3. Would you trust it with your own money, and what would change that?
  4. Which words should we use?

## 5. Presentation
- **Verified statistics:**
  - At least 2.2B people have a vision impairment ([WHO, Feb 2026](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment)).
  - CAPTCHA is the #1 barrier for 1,539 screen-reader users ([WebAIM](https://webaim.org/projects/screenreadersurvey10/)).
  - About 5,000 US digital-accessibility suits were filed in 2025, about 70% against e-commerce ([UsableNet](https://info.usablenet.com/2025-year-end-report-on-web-accessibility-lawsuits)). Its tracker says 4,928, so say "about".
  - The EU Accessibility Act has applied since 28 Jun 2025 ([Directive 2019/882](https://eur-lex.europa.eu/eli/dir/2019/882/oj)).
- **Problem statement:** "Blind shoppers can find a product, then lose it at checkout to CAPTCHAs, popups and unlabelled buttons. Sightline makes the whole purchase conversational, and reads back every dollar before anyone pays."
- **Making the video accessible:**
  - Upload hand-corrected closed captions.
  - Narrate every on-screen action, which serves as integrated audio description ([W3C WAI](https://www.w3.org/WAI/media/av/)).
  - Show NVDA Speech Viewer and a keystroke overlay.
  - Slow NVDA down and say so on screen.
  - Use a tester's voice only with written consent.

## 6. Name check: "Sightline" is risky
- [Sightline Payments](https://sightlinepayments.com/news/sightline-payments-celebrates-15-years-completes-management-and-shareholder-led-recapitalization) is a $1B+ US payments fintech, the same industry as the sponsor.
- [RNIB's Sightline Directory](https://rnib.org.uk/sightline-directory/sightline-directory-content-information) serves the same audience.
- Sightline Institute is a Pacific Northwest think tank.
- The sight metaphor also centres sighted people.

**Alternatives:** quick searches found no shopping or payments product named **Readback** (the safety feature is the name) or **Say When**. Check the CIPO and USPTO trademark databases before committing.

## 10 MVP UX requirements (testable)
1. Every task can be completed with NVDA and the keyboard alone, with the screen curtain on.
2. NVDA announces each reply exactly once, with TTS off or on.
3. Results list at most 3 items, each as name, price and rating in 15 words or fewer.
4. "Repeat", "more", "spell that" and Esc work at any point.
5. No payment happens without a readback of item, quantity, shipping, tax, total and delivery date, plus a confirm and a typed PIN.
6. Spoken amounts are identical to the PayPal order breakdown and are never generated by the LLM.
7. A purchase over the cap is refused, stating the cap and the overage.
8. Visual claims are labelled "listing says" or "photo suggests". Unknowns get "not stated".
9. No time limits. Shortcuts use modifiers only. Focus stays visible at 400% zoom.
10. axe and Lighthouse show 0 critical issues, and both testers finish task 4.

## 3-minute video outline
- **0:00** Black screen. NVDA at real speed, then a tester's line (with consent). Captions on.
- **0:15** The problem: three statistics and the checkout dead end.
- **0:35** "A gift under $40": three short results, "what colour exactly?", listing says vs photo suggests, compare two.
- **1:35** Cart, then readback from the PayPal order. Typed PIN, capture, receipt read aloud. Speech Viewer and the keystroke overlay stay visible.
- **2:10** Safeguards: a cap breach, "cancel", and "the listing doesn't say".
- **2:30** The tester's verdict, and one change made because of their feedback.
- **2:45** Architecture in one line (agent tools, Orders v2 with the vaulted token) and the name.
