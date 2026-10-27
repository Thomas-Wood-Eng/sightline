"""Offline: write fictional demo reviews and a summary per product into catalog/reviews.json (Gemini free tier).

    python catalog/make_reviews.py          # resumes; products already done are skipped

Star ratings are chosen here, in code, so their average matches each product's catalogue rating; the model only
writes the words. Reviews and summaries are clearly labelled demo data and must not contain prices or numbers.
"""
import json, os, random, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from google.genai import types  # noqa: E402

from app import llm  # noqa: E402

OUT = ROOT / 'catalog' / 'reviews.json'
MODEL = os.environ.get('REVIEWS_MODEL', 'gemini-3.5-flash')
ABOUT = 'Fictional demo reviews written with Gemini for this prototype. They are not from real customers.'


def stars_for(p):
    """5-12 star ratings whose mean is within half a star-step of the catalogue rating."""
    rng = random.Random(p['id'])
    n = rng.randint(5, 12)
    stars, deficit = [5] * n, 5 * n - round(p['rating'] * n)
    while deficit > 0:
        i = rng.randrange(n)
        step = min(deficit, rng.choice([1, 1, 2, 3]), stars[i] - 1)
        stars[i] -= step
        deficit -= step
    return stars


def ask(prompt):
    for attempt in range(4):
        try:
            r = llm.client().models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type='application/json', temperature=1.0))
            return json.loads(r.text)
        except Exception as e:  # free tier: 429s and stalls; back off and retry
            print('  retry', attempt, type(e).__name__, str(e)[:100])
            time.sleep(20 * (attempt + 1))
    raise SystemExit('Gemini kept failing; run again later to resume.')


def main():
    products = json.loads((ROOT / 'catalog' / 'catalog.json').read_text(encoding='utf-8'))
    data = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    data['_about'] = ABOUT
    for p in products:
        if p['id'] in data:
            continue
        stars = stars_for(p)
        facts = {k: v for k, v in p['listing'].items() if v}
        texts = ask(f"""Write {len(stars)} short, varied, realistic customer reviews for this product, one per star rating,
in this order: {stars}. Each review is one or two plain sentences in a different voice, about real aspects of the
product (fit, feel, taste, build, use). Low ratings name a concrete problem. Do not mention prices, money, or numbers.
Product: {p['name']} ({p['category']}). Listing: {json.dumps(facts)}
Return a JSON list of {len(stars)} strings.""")
        if not isinstance(texts, list) or len(texts) != len(stars):
            print('bad review list for', p['id']); continue
        reviews = [{'stars': s, 'text': str(t).strip()} for s, t in zip(stars, texts)]
        time.sleep(5)
        summary = ask(f"""Summarise these customer reviews for a blind shopper. Return JSON:
{{"pros": [up to 3 short phrases], "cons": [up to 3 short phrases], "complaint": "the most repeated complaint in one
short phrase, or null if none repeats"}}. Plain words, no numbers, no prices.
Reviews: {json.dumps(reviews)}""")
        data[p['id']] = {'reviews': reviews, 'summary': summary}
        OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
        print(p['id'], len(reviews), 'reviews, mean', round(sum(stars) / len(stars), 2), 'vs', p['rating'])
        time.sleep(5)


if __name__ == '__main__':
    main()
