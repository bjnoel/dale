"""
Shared shipping configuration for all nurseries.

This module is now a thin re-export of stocklib.registry, which holds one
Nursery record per nursery (the single source of truth for shipping states,
display names, and local-delivery restrictions). Kept so existing callers can
continue to `from shipping import SHIPPING_MAP, NURSERY_NAMES, ...` unchanged.

New code should import from stocklib.registry directly.
"""
from stocklib.registry import (  # noqa: F401
    SHIPPING_MAP,
    NURSERY_NAMES,
    LOCAL_DELIVERY,
    QUARANTINE_STATES,
    delivery_label,
    nursery_ships_to,
    restriction_warning,
)
