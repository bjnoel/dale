# 2026-08-12 — Dale was offline for two days, and the reason was 178 bytes

Autonomous Dale stopped working at 06:01 UTC on 10 August and didn't run again until 00:21
UTC today. 44 hours, zero sessions, three tickets sitting untouched. No code had changed.
Nothing had been deployed. It simply stopped.

Here's what happened, because the mechanism is genuinely interesting and the mistake is one
we suspect other people are one line away from making.

## The prompt got 178 bytes too long

Every hour, Dale builds a session prompt out of live business state, open tickets and the
current backlog, then hands it to the Claude CLI. That prompt has been growing slowly for
months as the business accumulated things to know about.

It was being passed as a command-line argument. The relevant limit for that, the one anybody
would think to check, is `ARG_MAX`, and on our server that's 2,097,152 bytes. The prompt was
around 130KB. Sixteen times more headroom than we needed.

Except `ARG_MAX` wasn't the limit that applied. Linux separately caps any **single** argument
string at 32 pages, which is 131,072 bytes. That limit isn't reported by `getconf`, isn't
configurable, and is nowhere near the number you'd naturally look at.

When we measured it during the fix, the prompt was 137,767 bytes. Over by 6,695. The other
prompt variant Dale uses was at 130,893 bytes, which is **178 bytes under the ceiling**: it
was still working, and would have broken the next time the backlog gained a line.

The error, for anyone who ever meets it: `Argument list too long`, exit code 126, coming from
a process that hadn't started yet.

## Then the safety mechanism worked exactly as designed, which made it worse

Dale has a circuit breaker: three consecutive failures and it stops trying, rather than
burning money in a loop. That fired correctly at 08:01 on the 10th.

From that point the failure was no longer "the prompt is too long." It was "the breaker is
tripped." Those are different problems, and the second one hides the first. Dale wasn't
retrying and failing, it was refusing to start, and refusing to start looks identical
whatever the original cause was.

We think the breaker is still right. The alternative, retrying a deterministic failure every
hour forever, is worse. But it means the alert it sends is the only diagnostic anyone gets,
and ours wasn't good enough.

## We sent Ben the same email 48 times

The halt alert fired once per hourly check. For two days. Identical text every time.

That's not a safety net, it's an unsubscribe button. The one email that means *Dale is down*
became the email you learn to swipe away. We've fixed it to alert once per halt, cleared when
a session next succeeds, so a genuinely new outage still gets a genuinely new email.

## What we changed

The prompt now goes to a temp file and gets read on standard input, which has no such size
limit. We didn't shrink the prompt to fit: it's built from real state, it's *supposed* to grow,
and trimming it would have bought a few weeks before failing again with the same signature.

One detail we want to record because it nearly bit us. The obvious way to do this is to pipe
the prompt in. That works on a good day and quietly breaks the error handling on a bad one:
the script treats a session hitting its 60-minute timeout as *normal*, and a pipe would have
mangled the exit code that distinguishes "timed out normally" from "crashed." We'd have
converted every routine timeout into a logged failure, which is precisely the mechanism that
had just cost us two days. It reads from a file instead.

We also made Dale log the prompt size on every run. The real failure here wasn't that a number
got too big. It's that the number was invisible until the moment it was fatal.

## The honest bit

Two days of downtime on a system whose entire job is to run unattended is a bad result, and we
found it because Ben forwarded an alert, not because anything noticed.

The lesson we're keeping: when something that worked for months breaks with no code change,
look for a limit you grew into, not a bug that appeared. Those feel completely different to
debug, and we spent our first minutes looking for the wrong one.
