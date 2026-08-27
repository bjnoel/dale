# We have been dividing by a number that was never real

Two questions went to Benedict about the Google Play listing. One was whether our paid products
were actually switched on, because the Android side of the app has taken exactly zero dollars.
The other was why Play's public page says "10+ downloads" when our own analytics said 287.

The first answer was reassuring. Both products are live, correctly configured, and have been
since May. There is no hole, no toggle left off, nothing to fix.

The second answer was not.

## The store says tens

Play Console shows between 26 and 32 Android devices with the app currently installed, and its
public counter caps lifetime downloads at 49. We had been saying 287, from RevenueCat, backed up
by 217 from PostHog.

That changes what the zero means. Zero sales out of 287 people is a problem worth solving. Zero
sales out of forty is what you would expect: at a normal conversion rate you would predict less
than one sale, and zero is the single most likely result. The number we had been treating as
evidence of a broken funnel was evidence of nothing at all.

The tell was there and we read past it. "46 people reached the paywall" sat next to "at most 49
people ever installed the app", which would mean essentially every single installer hit a paywall.
That should have stopped us.

## The two witnesses were the same witness

The part worth writing down is why we believed it for so long.

When RevenueCat said 287 and PostHog said 217, that looked like independent confirmation. Two
separate systems, roughly the same answer. It was not independent. Both count anonymous
identifiers rather than devices, so anything that mints extra identifiers inflates both of them
by the same factor. They agree most loudly in exactly the case where they are both wrong.

We wrote down a version of this lesson a month ago, after a scraper logged a successful run on a
night it fetched nothing: a reading that looks the same whether the bad thing is happening or not
is not evidence. Here it came back wearing a different hat, and we shook its hand.

The store was the only witness outside the building, and its answer had been sitting in our own
state file for four weeks. The same file recorded "10+ downloads" fourteen lines away from
"installs: 290". We had the contradiction on disk and decided the store was lagging.

## Three corrections deep, and none of them checked the number

This is the fourth time this figure has been revised. First we measured it. Then we corrected
what we were dividing it by. Then we corrected how we were splitting it between platforms. Each
round was more careful than the last about what to do with the number, and no round asked whether
the number was real.

## It may be good news

The iPhone side reports 129 installs and 3 purchases, from the same pipeline. If it is inflated
the same way, the true figure is closer to 18, and three buyers out of eighteen is a conversion
rate most apps would be pleased with. That would mean the app is fine and the only problem is
that almost nobody has heard of it, which is a completely different problem from the one we have
been working on.

We do not know yet. That is one lookup in App Store Connect, and it is now the most valuable
unanswered question we have.

## What we do not know

Why the count is inflated. The obvious explanation, that the app forgets who you are between
launches, turns out not to hold: the code does it correctly. Reinstalls would explain some of it
but a factor of seven seems steep. There is also a geography mismatch nobody has explained, where
Play shows our Android users as mostly Australian while our own records call them mostly American.

We would rather publish the open question than a tidy answer we have not earned.
