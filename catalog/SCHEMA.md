# Catalogue format (shared contract between the catalogue builder and the app)

`catalog/catalog.json`: a list of products. All money is USD, as numbers with 2 decimals, and lives ONLY here (never in LLM output).

```json
{
  "id": "hoodie-01",                      // kebab-case, unique, stable
  "name": "Fleece-lined pullover hoodie",  // short, spoken first
  "category": "clothing",                 // clothing | kitchen | electronics | grocery | home | gifts
  "price": 34.99,
  "rating": 4.6, "review_count": 212,
  "shipping": 4.99, "delivery_days": 3,
  "seller": "Sightline Demo Store",
  "listing": {                            // what the (fake) seller states; "listing says"
    "description": "one or two plain sentences",
    "colour": "heather grey", "sizes": ["S","M","L","XL"], "material": "80% cotton, 20% polyester, fleece lining",
    "dimensions": null, "in_box": "1 hoodie", "condition": "new", "allergens": null, "care": "machine wash cold"
  },
  "image": "img/hoodie-01.jpg",           // relative to app/static/
  "image_credit": {"title": "...", "creator": "...", "license": "CC0|PDM|CC BY 4.0|...", "source_url": "...", "license_url": "..."}
}
```

Unknown listing fields are `null` (spoken as "not stated"), never guessed.

`catalog/catalog_enriched.json`: same list, each product plus an `"enriched"` object written offline (Lane 2) and reviewed by hand:

```json
"enriched": {
  "short": "Fleece-lined grey hoodie, kangaroo pocket",          // ≤ 10 words, no prices
  "description": "spoken description for a blind shopper, ≤ 60 words, no prices",
  "facts": [{"label": "colour", "value": "heather grey", "source": "listing"},
            {"label": "pocket", "value": "front kangaroo pocket", "source": "photo"}],   // source: listing | photo
  "qa": [{"q": "Is it warm?", "a": "...", "source": "listing|photo|not_stated"}],      // ~8-10, no prices
  "similar": ["hoodie-02", "sweater-01"]
}
```

Comparisons are computed by the app from these fields at runtime (cheapest, best rated, etc.), so numbers stay deterministic.
