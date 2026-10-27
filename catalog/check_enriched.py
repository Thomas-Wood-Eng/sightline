"""Review gate for catalog/catalog_enriched.json. Exit code 1 if any product fails.

Fails on: money in enriched text, photo-sourced claims about size/allergens/dimensions, missing fields,
description over 60 words, short over 10 words, bad sources, unknown/same-category-violating similar ids.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONEY = re.compile(r"\$|\bprices?d?\b|\bpricing\b|\d+(\.\d+)?\s*(dollars?|cents?|usd)\b|\b(dollars?|cents?|usd)\b", re.I)
RISKY = re.compile(r"\b(size[sd]?|sizing|fit|fits|measure\w*|dimensions?|length|width|height|cm|mm|inch\w*|"
                   r"litre|liter|ml|oz|ounces?|capacity|weigh\w*|grams?|kg|allerg\w*|nuts?|peanuts?|gluten|dairy|milk|soy|wheat|"
                   r"ingredients?)\b", re.I)
SOURCES_FACT, SOURCES_QA = {"listing", "photo"}, {"listing", "photo", "not_stated"}


def words(s):
    return len(s.split())


def check(p, ids):
    errs, e = [], p.get("enriched")
    if not isinstance(e, dict):
        return ["missing enriched"]
    for k in ("short", "description", "facts", "qa", "similar"):
        if not e.get(k):
            errs.append(f"missing {k}")
    if errs:
        return errs
    if words(e["short"]) > 10:
        errs.append(f"short has {words(e['short'])} words")
    if words(e["description"]) > 60:
        errs.append(f"description has {words(e['description'])} words")
    if not 8 <= len(e["qa"]) <= 10:
        errs.append(f"{len(e['qa'])} Q&As (want 8-10)")
    texts = [("short", e["short"]), ("description", e["description"])]
    for i, f in enumerate(e["facts"]):
        if not f.get("label") or not f.get("value") or f.get("source") not in SOURCES_FACT:
            errs.append(f"fact {i} malformed: {f}")
            continue
        texts += [(f"fact {i}", f["label"] + " " + f["value"])]
        if f["source"] == "photo" and RISKY.search(f["label"] + " " + f["value"]):
            errs.append(f"photo fact about size/allergen/dimension: {f['label']}: {f['value']}")
    for i, qa in enumerate(e["qa"]):
        if not qa.get("q") or not qa.get("a") or qa.get("source") not in SOURCES_QA:
            errs.append(f"qa {i} malformed: {qa}")
            continue
        texts += [(f"qa {i}", qa["q"] + " " + qa["a"])]
        if qa["source"] == "photo" and RISKY.search(qa["q"] + " " + qa["a"]):
            errs.append(f"photo Q&A about size/allergen/dimension: {qa['q']} -> {qa['a']}")
    for where, t in texts:
        if MONEY.search(t):
            errs.append(f"money in {where}: {t!r}")
    for s in e["similar"]:
        if s not in ids or ids[s] != p["category"] or s == p["id"]:
            errs.append(f"bad similar id {s}")
    return errs


def main(path=ROOT / "catalog/catalog_enriched.json"):
    cat = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {p["id"]: p["category"] for p in cat}
    bad = 0
    for p in cat:
        for err in check(p, ids):
            bad += 1
            print(f"{p['id']}: {err}")
    print(f"{len(cat)} products checked, {bad} problems")
    return 1 if bad else 0


def _selftest():
    ok = {"id": "a", "category": "home", "enriched": {"short": "Grey mug", "description": "A grey mug.",
          "facts": [{"label": "colour", "value": "grey", "source": "listing"}],
          "qa": [{"q": f"q{i}", "a": "a", "source": "listing"} for i in range(8)], "similar": ["b"]}}
    ids = {"a": "home", "b": "home"}
    assert check(ok, ids) == []
    for bad in ("It costs $5", "only 12 dollars", "great price"):
        p = json.loads(json.dumps(ok)); p["enriched"]["description"] = bad
        assert check(p, ids), bad
    p = json.loads(json.dumps(ok)); p["enriched"]["facts"].append({"label": "size", "value": "looks medium", "source": "photo"})
    assert check(p, ids)


if __name__ == "__main__":
    _selftest()
    sys.exit(main(*sys.argv[1:]))
