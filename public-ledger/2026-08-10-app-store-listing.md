# 2026-08-10 — One App Store listing instead of two

**Decision:** [DEC-274](../decisions/decision-log.md)

## What happened

The App Store listing for Treesmith existed twice: an Australian one and an American one.
App Store Connect keeps the app name, subtitle and description separately for each
language you offer, and the two had drifted apart. April's listing work went into the
Australian one only.

So the American listing was still the original copy from before any of that, and it said
the free tier holds 50 plants. The app allows 30. On the storefront that supplies 61% of
installs, we were advertising a free allowance twenty plants larger than the app gives,
to people who decide whether to pay on the day they install.

Benedict's question was the right one: can we just keep one?

## The check that mattered

Yes, but only one of the two can be deleted, and picking the wrong one would have thrown
away the good listing and kept the broken one.

App Store Connect designates one language as primary, and it serves every storefront that
has no listing of its own. That one cannot be removed. The question was which.

Checking the obvious storefronts was not enough. The UK, Canada, New Zealand, Ireland and
Singapore all showed the Australian listing, but every one of those is an
English-speaking storefront that might have been matching on language rather than falling
back to the primary. Japan, Germany, France, Brazil and Mexico have no such connection.
All five also showed the Australian listing, which is what settled it.

A fallback test run only on storefronts that share a language proves nothing.

## What shipped

The American listing is deleted. The Australian one now serves everywhere.

The 50-plants error is gone by deletion rather than correction, and the description was
corrected separately: it no longer says the one-time Pro purchase includes cloud backup,
which is a separate yearly subscription. That error had already been fixed on the website,
the press kit and the terms in July, and the two store listings were the pages it was
missed on, which are also the pages people buy from.

There was a free by-product. The American storefront had the app name "TreeSmith" with no
descriptive words in it, and the app name is the field that actually determines what
searches you appear in. It now inherits the Australian name. That was not the goal of the
cleanup, it just came with it.

## The advice that was wrong first

The first instruction given for the accompanying repo change was to delete a directory
from version control. It would have failed, because the directory was never tracked. And
it would not have helped anyway: the deploy script had the two languages hardcoded in a
list and rewrote that directory on every deploy, which would have quietly re-created the
listing that had just been deleted, on the next release.

Deleting the artefact does not help when a script regenerates it. The real fix was one
line in the deploy script, plus the comment above it that still claimed both languages
were in use.

## Worth being clear about

None of this is visible yet. Both storefronts still serve the previous release with the
old copy. These changes go live when the next version is released.

The Google Play listing still carries the same incorrect line about cloud backup. That is
a different console and a separate job, still outstanding.

## Cost

$0.
