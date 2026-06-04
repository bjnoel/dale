# Pending decisions (parallel-run inbox)

When several guide-building sessions run in parallel (see `docs/species-guide-rollout.md`), do NOT
edit `../decision-log.md` directly. Every branch inserts at the same spot, and every branch guesses
the same next DEC number, so the second and later branches hit a merge conflict the moment they land.

Instead, each run drops ONE fragment here, uniquely named so branches never collide:

    decisions/pending/<YYYY-MM-DD>-<slug>.md

Format (the first heading line becomes the DEC title; the date comes from the filename):

    # One-line title

    **Decided by:** Dale (parallel guide run)
    **Context:** ...
    **Decision:** ...
    (Why / Actions / Status / To revert, same shape as the entries in decision-log.md)

Do NOT put a DEC number in the fragment; numbers are assigned at close-out so two parallel runs
cannot pick the same one.

After the batch has merged, one serialized close-out folds every fragment into the log with fresh
sequential DEC numbers and deletes them:

    python3 tools/fold_pending_decisions.py            # or --dry-run to preview

This directory should normally be empty on `main` (only this README).
