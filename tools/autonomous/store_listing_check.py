#!/usr/bin/env python3
"""Does what the store says match what the app does?

The store description is edited by hand in App Store Connect and Play Console.
The limits it describes live in git. Nothing has ever compared the two, and the
copy has now been wrong twice and right once:

  * The US listing advertised "up to 50 plants ... all free" against a real
    `freePlantLimit` of 30 (DEC-262), for roughly four months.
  * Both listings described Pro as including cloud backup, when Cloud Backup is
    a separate auto-renewing yearly subscription that requires Pro (DEC-247).

Every one of those transitions, in both directions, was found by a human reading
the page by hand. This is the thing that notices the next one.

Deliberately NOT a snapshot diff. A diff fires on every marketing reword, gets
muted inside a month, and then misses the one change that matters. Each rule here
asserts a claim in the copy against ground truth parsed out of the Flutter app,
so a rewrite that keeps the product description true stays silent, and a rewrite
that does not, does not.

Report only. Every field is Benedict's to paste; this never edits a listing.

Usage:
    python3 store_listing_check.py              # table to stdout, exit 1 on a failure
    python3 store_listing_check.py --json
    python3 store_listing_check.py --store ios --country US
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request

APP_MIRROR = "/opt/dale/treesmith-app"
ENTITLEMENTS = "lib/core/providers/entitlement_provider.dart"

IOS_TRACK_ID = 6761506742
ANDROID_PACKAGE = "app.treesmith"

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
PLAY_DETAILS = "https://play.google.com/store/apps/details"

# Play serves a stripped page to an unrecognised client.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# The storefronts worth checking. iOS collapsed to a single en-AU localisation
# in DEC-274, so AU and US should now return identical copy; checking both is
# what would catch a localisation being re-created (deploy.sh:451 did exactly
# that once, commit 1acaee3).
DEFAULT_TARGETS = [("ios", "AU"), ("ios", "US"), ("android", "AU"), ("android", "US")]

TIMEOUT_S = 30


class Unavailable(Exception):
    """A storefront could not be read. Never reported as a passing check."""


# --------------------------------------------------------------------------
# Ground truth: the app, not a copy of today's text
# --------------------------------------------------------------------------

def app_limits(mirror=APP_MIRROR):
    """Parse the real free-tier limits out of the Flutter source."""
    path = os.path.join(mirror, ENTITLEMENTS)
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    limits = {}
    for name in ("freePlantLimit", "freeLocationLimit"):
        match = re.search(rf"\b{name}\s*=\s*(\d+)", source)
        if not match:
            # The constant was renamed or removed. That is a real change to the
            # product, and silently checking nothing would be the worst outcome.
            raise Unavailable(f"{name} not found in {path}")
        limits[name] = int(match.group(1))
    return limits


# --------------------------------------------------------------------------
# Fetching live copy
# --------------------------------------------------------------------------

def _get(url, timeout=TIMEOUT_S):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_ios(country, timeout=TIMEOUT_S):
    url = f"{ITUNES_LOOKUP}?id={IOS_TRACK_ID}&country={country}"
    payload = json.loads(_get(url, timeout))
    results = payload.get("results") or []
    if not results:
        raise Unavailable(f"iTunes lookup returned no result for country={country}")
    entry = results[0]
    return {
        "name": entry.get("trackName", ""),
        "description": entry.get("description", ""),
        "version": entry.get("version", ""),
    }


def _play_description(page_html):
    """Pull the long description out of a Play details page.

    Anchored on `data-g-id="description"`, the attribute Play uses to mark the
    block, rather than on a class name (which is minified and rotates).
    """
    match = re.search(
        r'data-g-id="description"[^>]*>(.*?)</div>', page_html, re.DOTALL
    )
    if not match:
        raise Unavailable("could not locate the description block on the Play page")
    body = re.sub(r"<br\s*/?>", "\n", match.group(1))
    body = re.sub(r"<[^>]+>", "", body)
    return html.unescape(body).strip()


def fetch_android(country, timeout=TIMEOUT_S):
    url = f"{PLAY_DETAILS}?id={ANDROID_PACKAGE}&hl=en&gl={country}"
    page = _get(url, timeout)
    name = ""
    name_match = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', page, re.DOTALL)
    if name_match:
        name = html.unescape(re.sub(r"<[^>]+>", "", name_match.group(1))).strip()
    return {
        "name": name,
        "description": _play_description(page),
        "version": "",
    }


FETCHERS = {"ios": fetch_ios, "android": fetch_android}


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def _sentences(description):
    parts = re.split(r"(?<=[.!?])\s+|\n+", description)
    return [p.strip() for p in parts if p.strip()]


def free_plant_number(description):
    """The plant count the listing promises on the free tier, or None."""
    for sentence in _sentences(description):
        low = sentence.lower()
        if "free" not in low and not low.startswith("up to"):
            continue
        match = re.search(r"\b(?:up to\s+)?(\d+)\s+plants\b", low)
        if match:
            return int(match.group(1)), sentence
    return None, None


def _pro_sentences(description):
    """Sentences that describe what Pro includes.

    A sentence naming Pro before a colon or as the subject, not one that merely
    mentions Pro as a prerequisite ("requires Pro"), which is how Cloud Backup
    is legitimately described.
    """
    found = []
    for sentence in _sentences(description):
        low = sentence.lower()
        if not re.search(r"\bpro\b", low):
            continue
        if re.search(r"\b(requires|require|with|after)\s+(treesmith\s+)?pro\b", low):
            continue
        if re.match(r"\s*pro\b|.*\bpro[,:]", low):
            found.append(sentence)
    return found


def check_description(description, limits):
    """Run every rule. Returns a list of {rule, ok, detail} dicts."""
    findings = []

    def add(rule, ok, detail):
        findings.append({"rule": rule, "ok": ok, "detail": detail})

    low = description.lower()

    # 1. The free plant limit the listing promises must be the one we enforce.
    stated, sentence = free_plant_number(description)
    expected = limits["freePlantLimit"]
    if stated is None:
        add("free_plant_limit", False,
            "no free-tier plant count found in the description; "
            f"cannot confirm the listing matches freePlantLimit={expected}")
    elif stated != expected:
        add("free_plant_limit", False,
            f"listing promises {stated} free plants, app enforces {expected}: {sentence!r}")
    else:
        add("free_plant_limit", True, f"{stated} free plants, matches freePlantLimit")

    # 2. Pro is a one-time purchase, not a subscription. Getting this wrong once
    #    put incorrect pricing on four separate surfaces (CLAUDE.md, 2026-07-27).
    pro = _pro_sentences(description)
    if not pro:
        add("pro_is_one_time", False, "no sentence describing what Pro includes")
    elif not any("one-time" in s.lower() or "one time" in s.lower() for s in pro):
        add("pro_is_one_time", False,
            f"Pro is not described as a one-time purchase: {pro!r}")
    else:
        add("pro_is_one_time", True, "Pro described as a one-time purchase")

    # 3. Pro must not be described as including cloud backup. This is the
    #    DEC-247 defect, live on both stores for roughly three months.
    offending = [s for s in pro if "cloud backup" in s.lower()]
    if offending:
        add("pro_excludes_cloud_backup", False,
            f"a Pro feature list names cloud backup: {offending!r}")
    else:
        add("pro_excludes_cloud_backup", True, "Pro feature list does not claim cloud backup")

    # 4. Cloud Backup must be present and described as a separate subscription
    #    that requires Pro. Its absence would be as wrong as a misdescription:
    #    it is the only recurring product we sell.
    if "cloud backup" not in low:
        add("cloud_backup_described", False, "cloud backup is not mentioned at all")
    elif not re.search(r"cloud backup[^.]{0,120}\bsubscription\b", low):
        add("cloud_backup_described", False,
            "cloud backup is mentioned but not described as a subscription")
    elif not re.search(r"cloud backup[^.]{0,160}requires\s+(treesmith\s+)?pro", low):
        add("cloud_backup_described", False,
            "cloud backup is not stated to require Pro")
    else:
        add("cloud_backup_described", True,
            "cloud backup described as a subscription requiring Pro")

    return findings


def check(targets=None, mirror=APP_MIRROR, fetchers=None):
    """Check every storefront. Returns a result dict; never raises on one bad store."""
    targets = targets or DEFAULT_TARGETS
    fetchers = fetchers or FETCHERS
    limits = app_limits(mirror)

    listings = []
    for store, country in targets:
        entry = {"store": store, "country": country}
        try:
            live = fetchers[store](country)
            entry.update(live)
            entry["findings"] = check_description(live["description"], limits)
            entry["error"] = None
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["findings"] = []
        listings.append(entry)

    # 5. Storefronts must not silently diverge on the free-tier number. This is
    #    the DEC-262 defect: AU and US were different listings and only one was
    #    ever maintained, so a per-store check alone would have passed on AU.
    numbers = {}
    for entry in listings:
        if entry["error"]:
            continue
        stated, _ = free_plant_number(entry["description"])
        numbers[f"{entry['store']}/{entry['country']}"] = stated
    divergence = None
    distinct = set(numbers.values())
    if len(distinct) > 1:
        divergence = f"storefronts disagree on the free plant limit: {numbers}"

    unreadable = [e for e in listings if e["error"]]
    failures = [
        (e, f) for e in listings for f in e["findings"] if not f["ok"]
    ]
    return {
        "limits": limits,
        "listings": listings,
        "divergence": divergence,
        "failures": failures,
        "unreadable": unreadable,
        "ok": not failures and not divergence and not unreadable,
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def render(result):
    lines = []
    limits = result["limits"]
    lines.append(
        f"Ground truth from the app: freePlantLimit={limits['freePlantLimit']}, "
        f"freeLocationLimit={limits['freeLocationLimit']}"
    )
    lines.append("")
    for entry in result["listings"]:
        label = f"{entry['store']}/{entry['country']}"
        if entry["error"]:
            lines.append(f"  {label:14} UNREADABLE  {entry['error']}")
            continue
        name = entry.get("name") or "?"
        lines.append(f"  {label:14} {name}")
        for finding in entry["findings"]:
            mark = "ok  " if finding["ok"] else "FAIL"
            lines.append(f"      {mark} {finding['rule']}: {finding['detail']}")
    if result["divergence"]:
        lines.append("")
        lines.append(f"  FAIL divergence: {result['divergence']}")
    lines.append("")
    if result["ok"]:
        lines.append("All listings match the app.")
    else:
        lines.append(
            f"{len(result['failures'])} failing check(s), "
            f"{len(result['unreadable'])} unreadable storefront(s)."
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--store", choices=sorted(FETCHERS), help="limit to one store")
    parser.add_argument("--country", help="limit to one storefront code, e.g. US")
    parser.add_argument("--mirror", default=APP_MIRROR, help="path to the treesmith-app mirror")
    args = parser.parse_args(argv)

    targets = [
        (store, country)
        for store, country in DEFAULT_TARGETS
        if (not args.store or store == args.store)
        and (not args.country or country == args.country.upper())
    ]
    if not targets:
        parser.error("no storefront matches that --store/--country combination")

    result = check(targets=targets, mirror=args.mirror)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(render(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
