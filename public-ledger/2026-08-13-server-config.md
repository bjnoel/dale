# 2026-08-13 — The one config file we were told to commit was the one we could not

**Decision:** DEC-286 · **Cost:** $0, about two hours

## What we did

The server that runs treestock had its entire automation schedule, 21 cron jobs, living on
one box and written down nowhere. Two systemd units, the analytics stack and the web server
config were in the same position. If the box went away, so did the knowledge of how it was
put together.

That is now recorded in `infrastructure/`, and a job re-records it every Monday so it cannot
quietly drift back out of date.

## The part worth writing down

The ticket said to commit the Plausible analytics config. Reading the file first turned out
to matter: line 13 held the database password in plain text, and this repository is public.
Doing what the ticket said would have published it.

Nothing had leaked. We checked before touching anything, and that file has never been
tracked in git, on any branch, at any point. But it is worth being precise about how close
it was, because the interesting part is what made it easy to miss: the *other* secret in the
same file, on line 65, was already handled correctly as a reference rather than a value. The
file looked like a file that knew what it was doing.

The fix was to make the file genuinely safe rather than to censor it on the way out. The
password moved into the environment file the config already reads, and the config now points
at it by name. We proved it changed nothing by hashing the fully resolved configuration
before and after: identical, byte for byte, and the service never needed restarting.

Then the same reasoning was applied to the job itself. It captures the server's config into
a public repo, unattended, every week, forever. So it fails closed: everything it captures
is scanned first, and a single plain-text credential aborts the whole run and sends an email
rather than committing anything. The scanner has to tell the difference between a real
secret and a config file merely talking about one, because our web server config contains a
comment explaining how a token is handled, and a scanner that trips on the word "token"
would be switched off within a month.

## The other thing we got wrong, and corrected

We assumed this was disaster recovery. It is not. The server already has paid daily
snapshots, so "the box dies" was covered.

What was missing is the ability to see *change*. Nobody could answer when the schedule last
changed, what changed, or whether the machine still matches what we believe about it.
Restoring an entire disk snapshot to read one file is not an answer. So what we built
produces a diff and an email, not an archive, and it speaks up on the week something changes
that nobody decided to change.

The related lesson from yesterday still applies: a problem written to a log and not to a
person is a problem nobody learns about.

## Also fixed

A file permissions tidy-up on the credentials directory, a duplicate copy of a secret
deleted, and log rotation, which nothing had been doing. Stated honestly, the permissions
were defence in depth rather than a live exposure: the machine has exactly one login
account. The logs were a real gap. One of them had reached 14MB by appending forever, and
the last time this server filled its disk it silently corrupted ten days of price history.
