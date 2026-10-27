"""Lane 2 offline enrichment: photo + listing -> accessible description, facts and Q&As (catalog/catalog_enriched.json).

Usage: python catalog/enrich.py [--force id1,id2]
Per-product results are cached in catalog/enrich_cache/<id>.json, so reruns only call Gemini for missing/forced items.
Prices and shipping are never sent to the model, so it cannot repeat them.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors

ROOT = Path(__file__).resolve().parent.parent
CAT, OUT, CACHE = ROOT / "catalog/catalog.json", ROOT / "catalog/catalog_enriched.json", ROOT / "catalog/enrich_cache"
# Free key limits (AI Studio): Pro = 0 requests, Flash = 5/min and 20/day, Flash-Lite = 15/min and 500/day.
# So Lane 2 runs on Flash-Lite; a cached result keeps the model that wrote it in "_model".
MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
PAUSE = 6  # seconds between call starts: at most ~11 requests/minute (limit 15)
WORKERS = 2


class Fact(BaseModel):
    label: str
    value: str
    source: Literal["listing", "photo"]


class QA(BaseModel):
    q: str
    a: str
    source: Literal["listing", "photo", "not_stated"]


class Enriched(BaseModel):
    short: str = Field(description="10 words or fewer")
    description: str = Field(description="60 words or fewer")
    facts: list[Fact]
    qa: list[QA]


PROMPT = """You write product information for blind and low-vision shoppers, who will hear it read aloud by a screen reader.
You get one product photo and the seller's listing as JSON. Return JSON matching the schema.

Hard rules:
1. Never mention price, cost, money, value for money, discounts, shipping cost, or any currency. Do not use the word "price".
2. Every fact and answer has a source:
   - "listing": the information is stated in the listing JSON. Use the listing's exact wording for colours, sizes, materials, dimensions and allergens.
   - "photo": only visible in the photo, not in the listing. Phrase it as uncertain: "appears to have...", "the photo seems to show...".
     Photo facts may only describe visible appearance (shape, pattern, details, how it looks). Never use the photo for size, fit,
     dimensions, capacity, weight, allergens, ingredients, materials or anything about safety.
   - "not_stated": the listing does not say and it cannot be safely judged from the photo. Answer exactly
     "Not stated in the listing." and optionally one short next step, e.g. "You could ask the seller."
3. Never guess size, fit, allergens or dimensions. If the listing field is null, the answer is "not_stated".
4. If the photo shows things the listing does not include (props, other items, people, food on a board), make clear they are
   not part of the product. If the photo and listing disagree, trust the listing and mention the photo may differ.
5. Do not name brands or read logos shown in the photo.
6. For food, never name ingredients, nuts or allergens from the photo; only the listing may state them. For any product,
   photo facts never mention measurements, markings of volume, or sizes.
7. Only describe photo details you can see clearly; skip anything small, blurred, pixelated or ambiguous. In the
   description, any detail that comes only from the photo must also be hedged ("appears to...").
8. Ask about allergens only for food (category "grocery"). For other products do not ask about allergens.
9. Plain, concrete, friendly language. No marketing hype, no exclamation marks, no "stunning", no "perfect".

Fields:
- short: at most 10 words (count them), what it is plus the exact listing colour if there is one.
- description: 60 words or fewer, spoken first: what it is, exact colour, material and feel, notable details. No price.
- facts: 6 to 10 short label/value facts. Include every non-null listing field (colour, sizes, material, dimensions, in_box,
  condition, allergens, care), plus 1 to 3 "photo" facts about visible details.
- qa: 8 to 10 questions a blind shopper would ask about this product, with short answers (1-2 sentences). Cover:
  exact colour; size and fit (or capacity/dimensions for non-clothing); material, texture and how it feels; what is in the box;
  allergens and ingredients (food only); care or cleaning; what the reviews say;
  and one or two product-specific questions. For reviews, answer only "It has N reviews averaging R out of 5 stars."
  using review_count and rating from the listing, with source "listing". Never invent review quotes.
  For "is it in style" type questions, describe the look neutrally (source "photo") without claiming trends.

Product listing JSON:
"""


def load_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("GEMINI_API_KEY missing from .env")


def listing_for_model(p):
    # shortcut: rating/review_count are numbers but not money; price and shipping are deliberately left out.
    return {k: p[k] for k in ("name", "category", "rating", "review_count")} | {"seller_listing": p["listing"]}


dead = set()  # models that returned quota/unavailable during this run


def generate(client, p):
    img = (ROOT / "app/static" / p["image"]).read_bytes()
    contents = [types.Part.from_bytes(data=img, mime_type="image/jpeg"),
                PROMPT + json.dumps(listing_for_model(p), indent=1)]
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Enriched, temperature=0.2)
    for model in MODELS:
        if model in dead:
            continue
        for attempt in range(4):
            try:
                r = client.models.generate_content(model=model, contents=contents, config=cfg)
                return model, Enriched.model_validate_json(r.text).model_dump()
            except errors.APIError as e:
                # 404, or a second 429 in a row (per-minute limit hit twice): give up on this model, use the fallback
                if e.code == 404 or (e.code == 429 and attempt > 0 and model != MODELS[-1]):
                    print(f"  {model}: unavailable ({e.code}), falling back", flush=True)
                    dead.add(model)
                    break
                if e.code in (429, 500, 503, 504) and attempt < 3:
                    wait = 30 * 2 ** attempt
                    print(f"  {model}: {e.code}, retry in {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                raise
    raise RuntimeError("no model available")


def similar(p, cat):
    same = [q for q in cat if q["category"] == p["category"] and q["id"] != p["id"]]
    return [q["id"] for q in sorted(same, key=lambda q: abs(q["price"] - p["price"]))[:3]]


def main():
    force = set(sys.argv[sys.argv.index("--force") + 1].split(",")) if "--force" in sys.argv else set()
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    CACHE.mkdir(exist_ok=True)
    client = genai.Client(api_key=load_key(), http_options=types.HttpOptions(timeout=900_000))
    todo = [p for p in cat if p["id"] in force or not (CACHE / f"{p['id']}.json").exists()]

    def run(p):
        try:
            model, data = generate(client, p)
        except Exception as e:  # keep going; a rerun retries only the missing ones
            print(f"  {p['id']}: FAILED {str(e)[:200]}", flush=True)
            return
        data["_model"] = model
        (CACHE / f"{p['id']}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {p['id']}: ok via {model}", flush=True)

    # Starts are spaced by PAUSE, which is what keeps us under the per-minute limit.
    with ThreadPoolExecutor(WORKERS) as pool:
        for p in todo:
            print(f"start {p['id']}", flush=True)
            pool.submit(run, p)
            time.sleep(PAUSE)
    out, missing = [], []
    for p in cat:
        f = CACHE / f"{p['id']}.json"
        if not f.exists():
            missing.append(p["id"])
            continue
        e = json.loads(f.read_text(encoding="utf-8"))
        e.pop("_model", None), e.pop("_hand_edited", None)
        e["similar"] = similar(p, cat)
        out.append(p | {"enriched": e})
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(out)} products to {OUT.name}; missing: {missing or 'none'}")


if __name__ == "__main__":
    main()
