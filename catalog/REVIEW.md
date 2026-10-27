# Catalogue review list (for the human reviewer)

Generated text: `catalog/catalog_enriched.json` (cache: `catalog/enrich_cache/`, model `gemini-3.5-flash-lite` for all 40).
`python catalog/check_enriched.py` prints 0 problems. Below: everything flagged so far and what was done. Items marked
OPEN still need a human look.

## Photos: trademarks and people (video rules)

| Product | Problem | Resolution |
|---|---|---|
| hoodie-02 | Large "SUPERIOR" print | RESOLVED: new photo, a plain black pullover hoodie (Commons, public domain). The wearer's face is hidden by the hood; a small chest mark is pixelated. Listing now says plain black pullover (no zip-up photo existed) |
| raincoat-01 | Showed a young child | RESOLVED: new photo, a burnt-orange hooded rain jacket on a stand (CC BY 2.0); the pocket label is pixelated. The listing is now an adult jacket; `sizes` stays null on purpose |
| teddy-01 | Brand tag in the ear | RESOLVED: new photo, a plain cream teddy (museum photo, CC BY 4.0); the listing colour is now cream and the scarf is gone |
| sneakers-01 | Side label | RESOLVED: label pixelated (CC BY 2.0 allows changes; noted in CREDITS.md) |
| powerbank-01 | Brand logo | RESOLVED: new photo, a champagne-gold slim power bank (CC0); its faint logo is pixelated |
| keyboard-01 | Brand logo | RESOLVED: new photo, an off-white full-size wired keyboard (public domain); the console name is pixelated. Listing updated (full-size, wired, number pad); price is now $34.99 |
| charger-01 | Brand name on the front | RESOLVED: pixelated |
| earbuds-01 | Logos and markings on the case and buds | RESOLVED: new photo, plain lilac wired earphones (CC BY 4.0). The product is now "Wired in-ear earphones", price $14.99 |
| tshirt-01 | Identifiable face | RESOLVED: photo cropped at the neck (CC0) |
| knife-01, kettle-01, beanie-01, clock-01 | Brand text or logos (also found in these) | RESOLVED: pixelated |
| chocolate-01 | Brand embossed on every square | RESOLVED: new photo, unbranded dark chocolate chunks (CC BY 2.0). The product is now "Dark chocolate chunks, 70% cocoa" with the same allergens |
| journal-01 | Embossed "2017" on the cover | RESOLVED: pixelated. The listing now says pocket-sized A6, to match the photo |
| hoodie-01 | Person seen from behind | Kept: not identifiable |

## Generated text

| Product | Claim | Resolution |
|---|---|---|
| hoodie-01 | Photo fact "drawstring hood" (hard to see from behind) | RESOLVED: hand-edited to source `listing`, since the listing states a drawstring hood |
| hoodie-02 | Old "flame graphics on sleeves"; new draft said "relaxed fit" (a fit claim from the photo) | RESOLVED: new photo; the fit sentence was hand-replaced with "worn by a person with the hood up" |
| journal-01 | "embossed year"; A5 vs pocket-sized photo | RESOLVED: year pixelated, listing changed to A6; regenerated text describes only texture and the props (not included) |
| clock-01 | "hanging loop"; new draft named a "logo" and a time of day | RESOLVED: logo pixelated, regenerated; the time-of-day phrase was hand-removed |
| earbuds-01 | "indicator lights glowing" stated as fact | RESOLVED: new product photo; every photo claim in the new text is hedged |
| tshirt-01, teddy-01 (and other non-food) | "Are there any allergens listed?" | RESOLVED: prompt now asks about allergens only for grocery items; no non-food item has an allergen Q&A |
| raincoat-01 | "a small bag of food" prop | RESOLVED: new photo has no props |
| trail-mix-01, granola-01 | Model kept naming nuts "from the photo" | RESOLVED: hand-edited to quote the listing's allergen line (source `listing`) |
| keyboard-01 | "number pad" sourced to photo | RESOLVED: hand-edited to source `listing` |
| chocolate-01 | Draft said "baked squares" | RESOLVED: hand-edited to "rough, irregular dark pieces" |
| granola-01 | Photo seems to show cashews too; the listing names only almonds | OPEN: the text only quotes the listing. Consider adding cashews to the listing's allergen line, or accept |
| powerbank-01 | Photo claims: micro-USB port, power button, indicator lights | OPEN: all hedged and plausible; check against the photo |
| tshirt-01 | "subtle diamond texture" | Checked: visible in the photo; kept |

Cache files edited by hand carry `"_hand_edited": true`. Rerunning `enrich.py --force <id>` overwrites them, so redo the edit or recheck.
