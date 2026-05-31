"""
stocklib -- shared library for the treestock + beestock build and send pipelines.

Single source of truth for logic that used to be copy-pasted across builders,
scrapers, and email senders (and drift between them). Import the submodule you
need directly, e.g.:

    from stocklib.email_footer import inject_footer

It lives under tools/scrapers/ so it ships with the existing rsync deploy
(deploy.sh syncs tools/scrapers/ wholesale) with no extra packaging or install.
Scripts in tools/scrapers/ import it for free (their own dir is on sys.path);
scripts in tools/scrapers/bee/ add the parent dir to sys.path first.

This __init__ is intentionally thin (no eager submodule imports) so a script
that needs one helper does not pay to import the whole package.
"""
