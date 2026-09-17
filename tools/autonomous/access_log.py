#!/usr/bin/env python3
"""Summarise the treestock Caddy access log (DAL-294).

Every measurement treestock has ever made about who visits is Plausible, which
is a client-side JavaScript tag. That is the right tool for humans and blind to
everything else: a crawler does not run it, curl does not run it, and a fetch of
/shipping-reachability.json is not an HTML page so it *cannot* run it. The whole
point of publishing a CC BY dataset is that other people fetch it, and until now
a fetch was unobservable.

Three questions this answers and nothing else can:

  1. Is the published dataset actually being fetched, and by what?
  2. How is crawl attention split across page types? DAL-250 (DEC-266) had to
     record crawl budget as UNKNOWN for want of exactly this.
  3. Is anything getting PAST the Cloudflare AI-crawler block (DEC-269)? The
     ticket asked for the volume being turned away, and an origin log cannot
     answer that: a 403 issued at the edge never reaches us. Stated here rather
     than quietly answered on the requests that happen to arrive. That number
     needs the block off, which is DAL-246 and Benedict's dashboard toggle.

Report only. No thresholds, no alarms. DEC-323 and DEC-344 are both about
thresholds invented before the noise floor was measured, and this is a data
source nobody has ever looked at once.

KNOWN LIMIT, stated because it bounds every number below: this is the ORIGIN
log. Cloudflare sits in front and serves its cached assets without ever asking
us, so /styles.css and /dashboard.js are undercounted by an unknown amount.
HTML is not cached by default, which is the part these questions are about.
"""

import gzip
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

ACCESS_LOG = "/var/log/caddy/treestock-access.log"

# The dataset and the machine-readable index: the two files whose entire purpose
# is being fetched by something that is not a browser.
WATCHED_PATHS = ("/shipping-reachability.json", "/llms.txt")

# Ordered: first match wins, so the specific families sit above the generic
# "looks like a browser" test. Matched case-insensitively against the raw UA.
AGENT_CLASSES = (
    ("ai", (
        "gptbot", "oai-searchbot", "chatgpt-user", "claudebot", "claude-user",
        "claude-searchbot", "anthropic-ai", "perplexitybot", "perplexity-user",
        "ccbot", "bytespider", "amazonbot", "meta-externalagent",
        "google-extended", "applebot-extended", "cohere-ai", "diffbot",
        "imagesiftbot", "omgili", "youbot", "timpibot", "ai2bot",
    )),
    ("search", (
        "googlebot", "bingbot", "duckduckbot", "applebot", "yandex",
        "baiduspider", "slurp", "sogou", "petalbot", "seznambot",
        "google-inspectiontool", "adsbot-google", "mediapartners-google",
    )),
    ("seo", (
        "ahrefsbot", "semrushbot", "dotbot", "mj12bot", "blexbot",
        "dataforseobot", "barkrowler", "zoominfobot", "serpstatbot",
    )),
    ("monitor", (
        "uptime", "pingdom", "statuscake", "site24x7", "betteruptime",
    )),
    ("tool", (
        "curl/", "wget/", "python-requests", "python-urllib", "go-http-client",
        "java/", "okhttp", "axios/", "node-fetch", "libwww-perl", "httpie",
        "postmanruntime", "scrapy",
    )),
)

_BROWSER_MARKERS = ("chrome/", "safari/", "firefox/", "edg/", "opr/", "gecko/")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){3,}[0-9a-fA-F]{0,4}\b")


def classify_agent(ua):
    """Bucket a user-agent string. Returns one of the AGENT_CLASSES keys,
    'browser', or 'other'.

    'browser' is not 'human'. It is 'claims to be a browser', which is what a
    log can honestly say: DEC-269 established that a made-up UA and a spoofed
    Googlebot both get served, so nothing here is identity, only a claim.
    """
    if not ua:
        return "other"
    low = ua.lower()
    for name, needles in AGENT_CLASSES:
        for needle in needles:
            if needle in low:
                return name
    if "bot" in low or "crawler" in low or "spider" in low:
        return "other_bot"
    if any(marker in low for marker in _BROWSER_MARKERS):
        return "browser"
    return "other"


def path_type(path):
    """Which kind of treestock page. Deliberately a local copy rather than an
    import of stocklib: builders deploy to /opt/dale/scrapers and the digest to
    /opt/dale/autonomous, so a cross-import does not resolve at runtime
    (DEC-343)."""
    if path == "/" or path == "/index.html":
        return "homepage"
    if path.startswith("/variety/"):
        return "variety"
    if path.startswith("/species/"):
        return "species"
    if path.startswith("/nursery/"):
        return "nursery"
    if path.startswith("/compare/"):
        return "compare"
    if path.startswith("/buy-"):
        return "species+state"
    if path.endswith(".xml"):
        return "sitemap"
    if path.endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico", ".webp")):
        return "asset"
    return "other"


def _open(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, errors="replace")


def log_files(access_log=ACCESS_LOG):
    """The live log plus any files Caddy has rolled off it.

    Caddy names a rolled file <stem>-<timestamp>.log[.gz] beside the original,
    so a 24h window that straddles a roll is otherwise silently half-counted.
    """
    directory = os.path.dirname(access_log) or "."
    stem = os.path.basename(access_log)
    base = stem[:-4] if stem.endswith(".log") else stem
    found = []
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    for name in sorted(names):
        if name == stem or (name.startswith(base + "-")
                            and (name.endswith(".log") or name.endswith(".log.gz"))):
            found.append(os.path.join(directory, name))
    return found


def read_records(since, access_log=ACCESS_LOG):
    """Yield parsed records with ts >= since. Unparseable lines are skipped:
    a half-written last line is normal in a log being appended to right now."""
    for path in log_files(access_log):
        try:
            with _open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    ts = rec.get("ts")
                    if not isinstance(ts, (int, float)):
                        continue
                    if datetime.fromtimestamp(ts, timezone.utc) < since:
                        continue
                    yield rec
        except OSError:
            continue


def summarise(since, access_log=ACCESS_LOG):
    """Counts only. Every question above is a count; none of them needs an IP,
    which is why the Caddyfile does not log one."""
    summary = {
        "total": 0,
        "by_class": Counter(),
        "by_status": Counter(),
        "watched": {p: Counter() for p in WATCHED_PATHS},
        "search_page_types": Counter(),
        "ai_agents": Counter(),
        "top_agents": Counter(),
        "leaked_ip_headers": Counter(),
        "available": False,
    }
    if not log_files(access_log):
        return summary
    summary["available"] = True

    for rec in read_records(since, access_log):
        req = rec.get("request") or {}
        headers = req.get("headers") or {}
        ua_list = headers.get("User-Agent") or []
        ua = ua_list[0] if ua_list else ""
        path = req.get("uri") or ""
        status = rec.get("status")
        cls = classify_agent(ua)

        summary["total"] += 1
        summary["by_class"][cls] += 1
        summary["by_status"][status] += 1
        summary["top_agents"][ua[:80] or "(none)"] += 1
        if cls == "ai":
            summary["ai_agents"][ua[:60]] += 1
        if cls == "search":
            summary["search_page_types"][path_type(path)] += 1
        if path in summary["watched"]:
            summary["watched"][path][cls] += 1

        # The Caddyfile deletes the four headers a client IP arrives in. If a
        # fifth ever appears, the promise in that comment is quietly false, so
        # check rather than trust it (DEC-343).
        for name, values in headers.items():
            if name in ("User-Agent", "Referer", "Cf-Ray", "Accept",
                        "Accept-Encoding", "Accept-Language", "Cf-Visitor"):
                continue
            for value in values:
                if _IPV4.search(value) or _IPV6.search(value):
                    summary["leaked_ip_headers"][name] += 1

    return summary


def render_lines(summary, hours=24):
    """Plain-text block for the digest. Returns [] when there is nothing to say
    yet, so the first night after deploy is quiet rather than misleading."""
    if not summary["available"]:
        return []
    lines = [f"== Origin access log (last {hours}h) =="]
    if not summary["total"]:
        lines.append("  No origin requests recorded. Caddy logging may have stopped.")
        return lines

    total = summary["total"]
    order = ["browser", "search", "ai", "seo", "tool", "monitor", "other_bot", "other"]
    parts = [f"{name} {summary['by_class'][name]}"
             for name in order if summary["by_class"][name]]
    lines.append(f"  {total} origin requests: " + ", ".join(parts))

    statuses = ", ".join(f"{s} x{n}" for s, n in
                         sorted(summary["by_status"].items(),
                                key=lambda kv: -kv[1])[:6])
    lines.append(f"  Status: {statuses}")

    for path in WATCHED_PATHS:
        counts = summary["watched"][path]
        n = sum(counts.values())
        if n:
            who = ", ".join(f"{c} {k}" for k, c in counts.most_common())
            lines.append(f"  {path}: {n} fetches ({who})")
        else:
            lines.append(f"  {path}: 0 fetches")

    if summary["search_page_types"]:
        mix = ", ".join(f"{t} {n}" for t, n in
                        summary["search_page_types"].most_common(6))
        lines.append(f"  Search crawlers by page type: {mix}")

    if summary["ai_agents"]:
        who = ", ".join(f"{k} x{n}" for k, n in summary["ai_agents"].most_common(5))
        lines.append(f"  AI agents reaching origin: {who}")
    else:
        # Not "no AI agents came". Cloudflare 403s them at the edge (DEC-269),
        # so a turned-away request never reaches this log at all. This line
        # measures leakage past the block, not demand for the content, and the
        # ticket's third question stays unanswerable until DAL-246 is decided.
        lines.append("  AI agents reaching origin: none. This counts what gets "
                     "PAST the Cloudflare block, not what it turns away "
                     "(DEC-269, DAL-246).")

    if summary["leaked_ip_headers"]:
        who = ", ".join(f"{k} x{n}" for k, n in
                        summary["leaked_ip_headers"].most_common())
        lines.append(f"  (!) PRIVACY: an IP-shaped value reached the log in {who}. "
                     "Add a delete for it in the Caddyfile log filter.")
    return lines


def render_html(summary, hours=24):
    lines = render_lines(summary, hours)
    if not lines:
        return ""
    body = "".join(f"<li>{line.strip()}</li>" for line in lines[1:])
    return (f"<h3>Origin access log (last {hours}h)</h3>"
            f"<ul style='margin:0'>{body}</ul>")


def collect(hours=24, access_log=ACCESS_LOG, now=None):
    now = now or datetime.now(timezone.utc)
    return summarise(now - timedelta(hours=hours), access_log)


if __name__ == "__main__":
    import sys
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    for line in render_lines(collect(window), window) or ["(no access log yet)"]:
        print(line)
