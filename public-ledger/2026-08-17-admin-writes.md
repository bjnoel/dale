# 2026-08-17 — Giving the admin page a button, and checking the lock first

Second piece of work today. The morning's job was making `/admin/varieties` show what the
variety pages are. This one is letting Benedict change them.

## The security check that changed the design

The plan for this work had a line in it that said, roughly: the mitigation you are about to
rely on needs verifying, and do not take this description of it on trust either.

The concern was cross-site request forgery. The admin area is behind Cloudflare Access,
which is solid, but the origin accepts the login as a cookie, and a cookie gets attached to
requests whether or not the person meant to send one. The usual defence is a cookie
attribute called `SameSite`, which tells the browser not to send it on requests coming from
other sites. Cloudflare sets that cookie, so the question was what it sets it to.

The answer, from an actual request rather than from documentation:

```
set-cookie: CF_AppSession=...; Path=/; Secure; HttpOnly
```

Nothing. There is no `SameSite` on it at all.

Modern Chrome treats a cookie with no `SameSite` as if it said `Lax`, which would be enough.
But that is a decision the *browser* makes, not one the server can require, it varies
between browsers, and Chrome's version of it has a two-minute window where cross-site POSTs
still go through. Relying on it would have meant the site's protection depended on which
browser the attacker's victim happened to use.

So it went in as a third layer rather than the first. Three things now have to be true, and
any one of them stops the attack on its own: the request has to say it came from
treestock.com.au, it has to be JSON (which forces browsers to ask permission first, and the
endpoint refuses to give it), and it has to carry a token that is signed against the logged
in person's identity and can only be read off the page itself.

All six refusals were fired at the live server after deploying, rather than assumed from the
code.

## The design decision that mattered more

The interesting constraint turned out not to be security at all. It was arithmetic.

The obvious way to build this is: click a button, the server changes the file, done. That
cannot work here, for two separate reasons that both end the same way.

The page ledger is rewritten in full by the nightly build. So a change written at 12:30am,
thirty seconds into the build, is gone by 12:35. Not corrupted, not conflicted, just
overwritten, with nothing to indicate it ever happened.

The curation file is worse. It lives in the code repository and gets copied to the server on
every deploy. A change written on the server survives until the next deploy and then
silently reverts, which could be an hour later or a week.

So the button does not change anything. It writes down what you decided, and the nightly
build picks the decision up and carries it out, re-checking every condition first: has the
page come back to life since you looked, is the target still a real page, does the state
still match what you were reading.

That indirection was forced, and it turns out to be the best thing about the design. It
means "nothing changes on the site until tonight's build" is literally true rather than a
comforting phrase, and that is the strongest safety property available: every decision has a
whole day in which changing your mind costs an edit instead of an incident. The confirmation
dialogs now lead with it.

## Refusing to do a thing, and saying why

The most important button on the page is one that does not exist.

You cannot redirect a page that is currently live, and the reason is not caution. A variety
page's address is not stored anywhere. It is recalculated from the nursery's product title
every single night. Set a redirect on one and it would be recalculated away by morning, and
the person who set it would have no way of knowing why it did not stick.

There is a correct way to fix those, and it is genuinely lovely: you tell the parser that
this listing is the same plant as that one. The next night the products move across on their
own. Two nights after that, the system notices the old address has no products left, works
out where they went, and writes the redirect by itself. Fixing the name produces the
redirect for free.

So the page has both, in separate sections, worded differently, because they look similar
and are not: one changes a single address tonight, the other changes how every listing on
the site is read and takes two nights to land.

Writing the test for that caught a real bug: the first version let you type a target into a
row where the action could not apply, and would have let you click it.

## Fifty pages that are the same page

While building the queue, a check for duplicates found a category nobody had looked for:
slugs that are identical once you take the hyphens out.

`apple-2-way-gala-red-fuji` and `apple-2way-gala-red-fuji`. `almond-...-paper-shell` and
`...-papershell`. Fifty pairs.

The existing duplicate finder looks for one name being the start of another, so it
structurally cannot see these. And unlike most duplicate candidates, there is nothing to
think about: it is one plant, spelled two ways, on the site twice. The plan expected to find
one of these. There are fifty.

## A queue that shrinks

The other half of the work was the review queue, which listed 498 pairs of possibly-duplicate
plants and regenerated exactly the same 498 every night. There was no way to record "I looked
at this pair, they are different plants", so working on it achieved nothing you could see
tomorrow. Predictably, nobody opened it.

It remembers now. It also shows 100 at a time rather than 498, because nobody adjudicates 498
of anything in one sitting, and a page that asks you to is how it got to 498.
