"""Product catalogue: load once, BM25 search with optional price/category filters."""
import json, os, re
from pathlib import Path

from rank_bm25 import BM25Okapi

DIR = Path(__file__).resolve().parent.parent / 'catalog'


def _load():
    pinned = os.environ.get('SIGHTLINE_CATALOG')  # tests pin the sample catalogue
    for name in ([pinned] if pinned else ['catalog_enriched.json', 'catalog.json', 'sample_catalog.json']):
        if (DIR / name).exists():
            products = json.loads((DIR / name).read_text(encoding='utf-8'))
            # extras.json: optional fields (colour variants, demo risk flags) kept apart from the generated catalogue
            extras = json.loads((DIR / 'extras.json').read_text(encoding='utf-8')) if (DIR / 'extras.json').exists() else {}
            for p in products:
                p.update(extras.get(p['id'], {}))
            return products
    return []


STOP = set('a an and the for of with to in on me my i im some something any find show want need looking please '
           'is it that this one ones get buy can you do have are'.split())


def tokens(text):
    # crude plural stemming so "hoodies" finds "hoodie"
    return [w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w
            for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP]


def _doc(p):
    e = p.get('enriched') or {}
    l = p.get('listing') or {}
    parts = [p['name'], p['name'], p['category'], l.get('description') or '', l.get('colour') or '',
             l.get('material') or '', e.get('short') or '', e.get('description') or '']
    parts += [f"{f['label']} {f['value']}" for f in e.get('facts', [])]
    return tokens(' '.join(parts))


PRODUCTS = _load()
BY_ID = {p['id']: p for p in PRODUCTS}
CATEGORIES = sorted({p['category'] for p in PRODUCTS})
_bm25 = BM25Okapi([_doc(p) for p in PRODUCTS]) if PRODUCTS else None
_docs = [set(_doc(p)) for p in PRODUCTS]


def search(query, max_price=None, category=None, limit=9):
    """Best matches first. An empty query lists everything in the filter, best rated first."""
    ok = [i for i, p in enumerate(PRODUCTS)
          if (max_price is None or p['price'] <= max_price) and (category is None or p['category'] == category)]
    q = tokens(query or '')
    if not q:
        return [PRODUCTS[i] for i in sorted(ok, key=lambda i: -PRODUCTS[i]['rating'])][:limit]
    scores = _bm25.get_scores(q)
    # BM25 idf can be ~0 on tiny catalogues, so also require a literal token hit
    hit = lambda i: any(t in _docs[i] for t in q)
    ranked = sorted((i for i in ok if hit(i)), key=lambda i: (-scores[i], -PRODUCTS[i]['rating']))
    return [PRODUCTS[i] for i in ranked][:limit]



def get(pid):
    return BY_ID.get(pid)
