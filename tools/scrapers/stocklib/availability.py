"""Supplier availability vocabulary and the waiting states' lead times.

A supplier feed can say a plant is purchasable today with a wait of months.
Daleys' feed has two such states and they are not the same wait, which is the
whole reason this module exists rather than a bare "pre-order" boolean.

Correy at Daleys, 2026-08-27, asked what separates them:

    PreSale is 1-2 months catalogue. Eg Spring Catalogue, Bare Root Catalogue.
    PreOrder is 1-6 months. when a plant is potted up after a successful graft
    or "cutting take"

So PreSale is a season the nursery has already committed to and PreOrder is a
propagation batch that has struck but is not potted on yet. Both are orderable
now; one is a wait you can plan around and the other is up to half a year and
depends on how the grafts came up. Collapsing them into one badge told a buyer
waiting on a Krasuey the same thing as a buyer waiting on a bare-root apple,
and the honest answer is different.

The strings live here, in one place, because three consumers need them and the
repo has been burnt by hand-synced copies before (see fruit_filters' docstring):

  - build-dashboard.py emits `wait` into data.js, dashboard.js renders `badge`
  - send_variety_alerts.py puts `email` in the "open for pre-order" alert, which
    used to tell the reader to go and look the wait up themselves
  - csv_feed_scraper.py maps the feed's raw vocabulary onto these keys

`order` exists so a product whose variants disagree rolls up to the longer
wait. Promising one to two months on a product where some sizes are six is the
failure that costs a nursery relationship, not the other way round.
"""
from __future__ import annotations

# Purchasable-with-a-wait states, longest wait last.
WAIT_STATES: dict[str, dict] = {
    "presale": {
        "order": 1,
        "badge": "Pre-order 1-2 mo",
        "email": "ready in one to two months",
        "why": "Ordered from a seasonal catalogue (spring, bare root). "
               "Daleys expect it ready in one to two months.",
    },
    "preorder": {
        "order": 2,
        "badge": "Pre-order 1-6 mo",
        "email": "ready in one to six months",
        "why": "Potted up after a successful graft or cutting strike. "
               "Daleys expect it ready in one to six months.",
    },
}

#: Every state a variant can be in, waiting ones included.
PURCHASABLE_STATES = frozenset({"instock", *WAIT_STATES})


def is_waiting(state: str | None) -> bool:
    """True for a state that is orderable now but not ready to ship."""
    return state in WAIT_STATES


def roll_up(states) -> str | None:
    """Product-level wait state from its variants', or None if none wait.

    Longest wait wins: a product with a 1-2 month size and a 1-6 month size is
    reported as 1-6, because the buyer who gets the long one was not warned by
    the short answer.
    """
    waiting = [s for s in states if s in WAIT_STATES]
    if not waiting:
        return None
    return max(waiting, key=lambda s: WAIT_STATES[s]["order"])


def badge(state: str | None) -> str:
    """Short badge text for a wait state. Falls back to the generic label so a
    snapshot written before the two states were split still renders."""
    if state in WAIT_STATES:
        return WAIT_STATES[state]["badge"]
    return "Pre-order"


def email_phrase(state: str | None) -> str:
    """Sentence fragment for alert copy, e.g. "ready in one to two months"."""
    if state in WAIT_STATES:
        return WAIT_STATES[state]["email"]
    return "not ready to ship yet"


def client_table() -> dict:
    """The subset dashboard.js needs, emitted once into data.js rather than
    repeated on every pre-order product."""
    return {k: {"b": v["badge"], "w": v["why"]} for k, v in WAIT_STATES.items()}
