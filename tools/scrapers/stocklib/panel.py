"""The per-nursery loop every multi-nursery scraper runs.

One nursery's crash is recorded and the loop moves on. Every scraper's main()
used to catch the exception, write ok=false, and then re-raise, so the first
nursery to crash took every nursery after it down with it. On 2026-09-27 to
09-29 Guildford, first in the WooCommerce dict, crashed on an unexpected API
response, and the seven WooCommerce nurseries after it never ran for three
nights ("only 19 of 26 nurseries ran; 7 never reported"). Shopify, Ecwid,
Squarespace and Wix had the same loop.
"""
import sys
import traceback

from stocklib.scrape_health import ScrapeHealth


def run_panel(targets, source, scrape_one, *, pause=None):
    """Call scrape_one(key, config, health) for each nursery in `targets`.

    scrape_one returns the keyword arguments for health.finish() (products,
    in_stock, priced), or None for finish()'s defaults. An exception is
    printed, recorded as ok=false, and the next nursery runs. `pause` is
    called between nurseries, not after the last.

    Exits 1 after the last nursery if any crashed, so run-all-scrapers.sh
    still reports the platform as failed. A failure that does not raise
    (zero products, a failed fetch) is left to the health record, as before.
    """
    crashed = []
    keys = list(targets)
    for i, key in enumerate(keys):
        health = ScrapeHealth(key, source=source)
        try:
            result = scrape_one(key, targets[key], health)
        except Exception as e:
            traceback.print_exc()
            health.note_error(repr(e))
            health.finish(ok=False)
            crashed.append(key)
        else:
            health.finish(**(result or {}))
        print()
        if pause and i < len(keys) - 1:
            pause()

    if crashed:
        print(f"Crashed: {', '.join(crashed)} (the other nurseries still ran)")
        sys.exit(1)
