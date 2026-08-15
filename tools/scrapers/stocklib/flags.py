"""
Site-wide feature switches for treestock.

One module so a switch is flipped in one place and every builder agrees, rather
than each page carrying its own commented-out block.
"""

# The daily/weekly digest signup, hidden across the site 2026-08-15.
#
# Why: after five months of prominent placement (homepage block, mobile
# floating bar, species/variety/when-to-plant pages, a dedicated
# /sample-digest.html preview, and the WA Rare Fruit Guide lead magnet) the
# digest had 12 subscribers and was going backwards, 3 unsubscribes against 2
# signups in the fortnight to 2026-08-15. Over the same period the per-variety
# "notify me" watch, which is a 12px pill on out-of-stock rows only, reached 89
# people holding 101 watches and grew every month. The watch also gets 33.3%
# click against the digest's 10.5%, and nobody has ever removed a watch after
# being alerted. The digest was crowding out the thing people actually want.
#
# This hides the SIGNUP only. Sends to existing subscribers continue, and
# /api/subscribe, /api/confirm, /preferences and /unsubscribe.html all stay
# live so in-flight confirmation links and manage links keep working.
#
# Set back to True to restore every signup surface at once.
DIGEST_SIGNUP_ENABLED = False
