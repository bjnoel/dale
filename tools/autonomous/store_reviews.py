#!/usr/bin/env python3
"""Ratings and written reviews for TreeSmith on both stores.

Benedict's ask (2026-09-21): the weekly mail should say how many reviews each
store holds, and when a new one lands, what it says. Both stores expose this
without credentials:

- iOS: the iTunes lookup carries `userRatingCount` and `averageUserRating`
  per storefront, and the public RSS feed
  `itunes.apple.com/{cc}/rss/customerreviews/id={id}/sortBy=mostRecent/json`
  carries the written reviews with title, body, stars, version and date.
  Ratings are per storefront, so AU and US are pulled separately.
- Android: the Play details page embeds `"ratingCount"` / `"ratingValue"`
  JSON-LD, but ONLY once the app has enough ratings for Play to display them.
  Below that threshold the markers are absent, which is not the same as zero:
  on 2026-09-21 the page had no marker while the reviews RPC returned one
  five-star written review. So the count is reported as "not shown yet" when
  the marker is missing, and written reviews come from the same batchexecute
  RPC (`UsvDTd`) the Play web client uses. Play reviews are global.

"New" means not seen by a previous run. Seen review ids live in a state file
(`/opt/dale/data/treesmith-store-reviews.json`); the first run reports every
review as new, which is correct for the first mail that carries them. The
state is only written on a fully successful fetch of a store, so a store that
failed this week reports its reviews as new next week rather than losing them.

Stdlib only, like the rest of the digest.
"""

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

IOS_TRACK_ID = 6761506742
ANDROID_PACKAGE = "app.treesmith"
IOS_COUNTRIES = ("au", "us")
PLAY_COUNTRY = "au"

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
ITUNES_REVIEWS = ("https://itunes.apple.com/{cc}/rss/customerreviews/"
                  "id={app_id}/sortBy=mostRecent/json")
PLAY_DETAILS = "https://play.google.com/store/apps/details"
PLAY_RPC = "https://play.google.com/_/PlayStoreUi/data/batchexecute"
# Newest first, up to this many. We only ever need the ones we have not seen.
PLAY_REVIEW_PAGE = 40

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_S = 30
STATE_NAME = "treesmith-store-reviews.json"
MAX_TEXT = 600


class Unavailable(RuntimeError):
    pass


def state_path(environ=None):
    environ = os.environ if environ is None else environ
    return os.path.join(environ.get("DALE_DATA", "/opt/dale/data"), STATE_NAME)


def _get(url, timeout=TIMEOUT_S, data=None, headers=None):
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _clip(text):
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 3] + "..."


# --------------------------------------------------------------------------
# iOS
# --------------------------------------------------------------------------

def fetch_ios(country, getter=_get):
    payload = json.loads(getter(
        f"{ITUNES_LOOKUP}?id={IOS_TRACK_ID}&country={country}"))
    results = payload.get("results") or []
    if not results:
        raise Unavailable(f"iTunes lookup returned no result for {country}")
    entry = results[0]
    feed = json.loads(getter(ITUNES_REVIEWS.format(cc=country,
                                                   app_id=IOS_TRACK_ID)))
    return {
        "store": "ios",
        "country": country.upper(),
        "rating_count": int(entry.get("userRatingCount") or 0),
        "average": entry.get("averageUserRating"),
        "reviews": parse_ios_feed(feed),
    }


def parse_ios_feed(feed):
    """Apple's RSS quirk: `entry` is a list with several reviews, a dict with
    one, and absent with none."""
    entries = (feed.get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        def lab(key):
            return ((e.get(key) or {}).get("label") or "").strip()
        rid = lab("id")
        if not rid:
            continue
        out.append({
            "id": f"ios:{rid}",
            "author": (e.get("author") or {}).get("name", {}).get("label", ""),
            "stars": int(lab("im:rating") or 0),
            "title": _clip(lab("title")),
            "text": _clip(lab("content")),
            "version": lab("im:version"),
            "date": lab("updated")[:10],
        })
    return out


# --------------------------------------------------------------------------
# Android
# --------------------------------------------------------------------------

def parse_play_page(page):
    """(rating_count, average) or (None, None) when Play is not showing them."""
    count = re.search(r'"ratingCount":"?(\d+)', page)
    value = re.search(r'"ratingValue":"?([0-9.]+)', page)
    if not count:
        return None, None
    return int(count.group(1)), (round(float(value.group(1)), 1)
                                 if value else None)


def _play_rpc_body(package, count=PLAY_REVIEW_PAGE):
    # Same shape google-play-scraper sends: sort 2 = newest, no page token.
    inner = json.dumps([None, None, [2, None, [count, None, None]],
                        [package, 7]])
    return urllib.parse.urlencode({
        "f.req": json.dumps([[["UsvDTd", inner, None, "generic"]]])
    }).encode("utf-8")


def parse_play_reviews(raw):
    """Unwrap the batchexecute envelope: `)]}'` prefix, then a JSON list whose
    first row holds the review payload as a JSON string."""
    body = raw.split("\n", 1)[1] if raw.startswith(")]}'") else raw
    outer = json.loads(body)
    inner = None
    for row in outer:
        if isinstance(row, list) and len(row) > 2 and row[0] == "wrb.fr":
            inner = row[2]
            break
    if inner is None:
        raise Unavailable("Play reviews RPC returned no wrb.fr row")
    payload = json.loads(inner) if isinstance(inner, str) else inner
    reviews = payload[0] if payload else []
    out = []
    for r in reviews or []:
        try:
            ts = r[5][0]
            date = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        except (IndexError, TypeError, ValueError):
            date = ""
        out.append({
            "id": f"android:{r[0]}",
            "author": (r[1][0] if r[1] else "") or "",
            "stars": int(r[2] or 0),
            "title": "",
            "text": _clip(html.unescape(r[4] or "")),
            "version": (r[10] if len(r) > 10 and isinstance(r[10], str)
                        else ""),
            "date": date,
        })
    return out


def fetch_android(country=PLAY_COUNTRY, getter=_get):
    page = getter(f"{PLAY_DETAILS}?id={ANDROID_PACKAGE}&hl=en&gl={country}")
    rating_count, average = parse_play_page(page)
    raw = getter(
        f"{PLAY_RPC}?rpcids=UsvDTd&hl=en&gl={country}",
        data=_play_rpc_body(ANDROID_PACKAGE),
        headers={"Content-Type":
                 "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    return {
        "store": "android",
        "country": "global",
        # None here means Play is not displaying a count yet, NOT zero.
        "rating_count": rating_count,
        "average": average,
        "reviews": parse_play_reviews(raw),
    }


# --------------------------------------------------------------------------
# State and the combined check
# --------------------------------------------------------------------------

def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"seen": []}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def check(fetchers=None, path=None, now=None, persist=True):
    """Return the per-store counts, the reviews not seen before, and errors.

    Never raises: a store that cannot be read is listed under `unreadable`
    with the reason, so the digest can say so instead of printing a zero.
    """
    fetchers = fetchers or {
        "ios": [lambda cc=cc: fetch_ios(cc) for cc in IOS_COUNTRIES],
        "android": [fetch_android],
    }
    path = path or state_path()
    state = load_state(path)
    seen = set(state.get("seen") or [])
    stores, new, unreadable = [], [], []
    fetched_ids = []
    for store, fns in fetchers.items():
        for fn in fns:
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001 - reported, not hidden
                unreadable.append({"store": store, "error": str(exc)})
                continue
            stores.append({k: v for k, v in res.items() if k != "reviews"}
                          | {"written": len(res["reviews"])})
            for r in res["reviews"]:
                fetched_ids.append(r["id"])
                if r["id"] not in seen:
                    new.append({"store": res["store"],
                                "country": res["country"]} | r)
    if fetched_ids and persist:
        state["seen"] = sorted(seen | set(fetched_ids))
        state["updated_at"] = (now or datetime.now(timezone.utc)).isoformat()
        try:
            save_state(path, state)
        except OSError as exc:
            unreadable.append({"store": "state", "error": str(exc)})
    return {"stores": stores, "new": new, "unreadable": unreadable,
            "first_run": not seen}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # A manual run never persists: the Monday digest owns the state file.
    result = check(persist="--dry-run" not in argv)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
