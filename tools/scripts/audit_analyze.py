#!/usr/bin/env python3
"""DEC-207 follow-up audit analysis. Runs on the server (imports stocklib).
Replicates each scraper's include-filter against ground truth and classifies
the dropped items as real fruit/nut/berry vs correctly-excluded junk."""
import json, sys, re
sys.path.insert(0, "/opt/dale/scrapers")
from stocklib.classify import is_real_product, is_junk_keyword, is_seed_packet, NON_PLANT_KEYWORDS
from stocklib.taxonomy import load_species, ENABLED_CATEGORIES

# Build a fruit/nut/berry/bush-tucker keyword set from the species taxonomy
# (common names + aliases of enabled categories) plus obvious generic tokens.
species = load_species()
FRUIT_WORDS = set()
for r in species:
    cat = r.get("category", "fruit")
    tags = r.get("tags", [])
    if cat in ENABLED_CATEGORIES or any(t in ENABLED_CATEGORIES for t in tags):
        cn = (r.get("common_name") or "").lower()
        if cn:
            FRUIT_WORDS.add(cn)
        for a in r.get("aliases", []) or []:
            FRUIT_WORDS.add(a.lower())
# generic fruit/nut/berry tokens that may not be exact common names
FRUIT_WORDS |= {
    "apple", "pear", "plum", "cherry", "apricot", "peach", "nectarine",
    "fig", "mulberry", "quince", "medlar", "pomegranate", "persimmon",
    "almond", "walnut", "chestnut", "hazelnut", "pecan", "macadamia",
    "grape", "kiwi", "blueberry", "currant", "raspberry", "blackberry",
    "gooseberry", "loganberry", "boysenberry", "tayberry", "olive",
    "citron", "lemon", "lime", "orange", "mandarin", "grapefruit",
    "kumquat", "tangelo", "pomelo", "feijoa", "guava", "loquat",
    "tamarillo", "passionfruit", "passion fruit", "avocado", "mango",
    "lychee", "longan", "tangerine", "nashi", "sloe", "damson",
    "berry", "nut", "citrus", "fruit", "rootstock",
}
# obvious non-fruit ornamental/junk tokens (for slug classification)
NONFRUIT_WORDS = {
    "rose", "roses", "crepe-myrtle", "crepe myrtle", "dogwood", "magnolia",
    "lilac", "weigela", "witch-hazel", "witch hazel", "crabapple", "crab-apple",
    "flowering", "ornamental", "smoke-bush", "smoke bush", "cotinus",
    "hazel", "label", "labels", "sharpener", "book", "tool", "tools",
    "voucher", "gift", "knife", "tape", "wax", "sealant", "stake", "guard",
    "fertil", "spray", "workshop", "weigela", "viburnum", "hydrangea",
    "camellia", "azalea", "rhododendron", "maple", "oak", "elm", "ash",
    "wisteria", "clematis", "jasmine", "lavender", "buddleja", "spirea",
    "quince-flowering", "almond-flowering",
}


def classify_slug_or_title(text):
    """Return 'fruit', 'nonfruit', or 'ambiguous' based on keyword hits."""
    t = text.lower().replace("-", " ")
    # crabapple/flowering are ornamental even though they contain 'apple'
    if any(nf.replace("-", " ") in t for nf in NONFRUIT_WORDS):
        # but a real fruit word still present and no junk? keep ambiguous unless clearly ornamental
        if "crabapple" in t.replace(" ", "") or "crab apple" in t or "flowering" in t \
           or "rose" in t or "ornamental" in t or "label" in t or "dogwood" in t \
           or "magnolia" in t or "myrtle" in t or "lilac" in t or "sharpener" in t \
           or "book" in t or "voucher" in t or "weigela" in t or "smoke bush" in t \
           or "witch hazel" in t or "cotinus" in t:
            return "nonfruit"
    if any(re.search(r"\b%s\b" % re.escape(fw), t) for fw in FRUIT_WORDS):
        return "fruit"
    return "ambiguous"


def shopify_filter_keep(p, nursery):
    pt = (p.get("product_type") or "")
    tags = p.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip().lower() for x in tags.split(",")]
    else:
        tags = [str(x).lower() for x in tags]
    if nursery == "garden-world":
        return pt.lower() in {"food plants"}
    if nursery == "diggers":
        ft = ["all fruit & nuts", "all fruit &amp; nuts", "all berries", "fruit trees", "nuts"]
        return any(f.lower() in tags for f in ft)
    if nursery == "forever-seeds":
        ft = ["fruit", "edible", "citrus"]
        return any(f.lower() in tags for f in ft)
    return True


def audit_shopify(nursery, seed_store=False):
    prods = json.load(open("/tmp/%s_catalog.json" % nursery))
    kept = [p for p in prods if shopify_filter_keep(p, nursery)]
    dropped = [p for p in prods if not shopify_filter_keep(p, nursery)]
    print("\n" + "=" * 72)
    print("%s: total=%d kept=%d dropped=%d" % (nursery, len(prods), len(kept), len(dropped)))
    print("=" * 72)
    # dropped product_type histogram
    from collections import Counter
    print("dropped product_type histogram:")
    for t, n in Counter((p.get("product_type") or "(empty)") for p in dropped).most_common(30):
        print("   %4d  %s" % (n, t))
    # candidate misses: dropped items that look like fruit and are NOT junk
    print("\nCANDIDATE MISSED FRUIT (dropped, fruit-keyword hit, not junk keyword):")
    candidates = []
    for p in dropped:
        title = p.get("title") or ""
        if is_junk_keyword(title):
            continue
        if not seed_store and is_seed_packet(title):
            continue
        cls = classify_slug_or_title(title)
        if cls == "fruit":
            candidates.append(p)
    for p in candidates:
        print("   - %-55s type=%-20r tags=%s" % (
            (p.get("title") or "")[:55], (p.get("product_type") or ""),
            (p.get("tags") if isinstance(p.get("tags"), list) else p.get("tags"))))
    print("  >>> %d candidate missed-fruit products" % len(candidates))
    return len(prods), len(kept), len(dropped), len(candidates)


print("ENABLED_CATEGORIES =", ENABLED_CATEGORIES)
print("FRUIT_WORDS count =", len(FRUIT_WORDS))

audit_shopify("garden-world")
audit_shopify("diggers")
audit_shopify("forever-seeds", seed_store=True)

# ---- Heritage (BigCommerce) ----
print("\n\n" + "#" * 72)
print("# HERITAGE (BigCommerce) sitemap-vs-captured diff")
print("#" * 72)
sitemap = [u.strip() for u in open("/tmp/hft_products.txt") if u.strip()]
sitemap_slugs = [u.rstrip("/").rsplit("/", 1)[-1] for u in sitemap]
cap = json.load(open("/opt/dale/data/nursery-stock/heritage-fruit-trees/latest.json"))
captured_slugs = set(p.get("handle") for p in cap["products"])
print("sitemap products=%d  captured=%d" % (len(sitemap_slugs), len(captured_slugs)))
missed = [s for s in sitemap_slugs if s not in captured_slugs]
print("missed (in sitemap, not captured)=%d" % len(missed))

# classify missed
buckets = {"fruit": [], "nonfruit": [], "ambiguous": []}
for s in missed:
    buckets[classify_slug_or_title(s)].append(s)
print("\nMISSED breakdown: fruit=%d nonfruit=%d ambiguous=%d" % (
    len(buckets["fruit"]), len(buckets["nonfruit"]), len(buckets["ambiguous"])))
print("\n--- MISSED that look like FRUIT/NUT/BERRY (candidate coverage gaps) ---")
for s in sorted(buckets["fruit"]):
    print("   ", s)
print("\n--- MISSED ambiguous (manual review) ---")
for s in sorted(buckets["ambiguous"]):
    print("   ", s)
