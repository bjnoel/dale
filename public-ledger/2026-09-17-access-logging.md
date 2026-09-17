# 2026-09-17 — Six months of publishing with no way to see a single fetch

**Ticket:** DAL-294 · **Decision:** DEC-345 · **Track:** treestock.com.au

## What was wrong

treestock's web server kept no access log. Everything we know about who visits
comes from Plausible, which is a small piece of JavaScript that runs in a
visitor's browser. That works for people and is blind to everything else: search
crawlers do not run JavaScript, `curl` does not run it, and
`/shipping-reachability.json` is not a web page at all, so it cannot run it even
in principle.

Three weeks ago we published that file as an open CC BY 4.0 dataset and invited
people to cite it. Until today, a download of it left no trace anywhere.

## What we turned on

A JSON access log on the treestock site, rolled and aged out by the web server
itself, plus a short nightly summary in the internal digest: requests by kind of
client, status codes, and fetches of the dataset and `/llms.txt` specifically.

It is a report, not an alarm. We have never once looked at this data, so we have
no idea what a normal night looks like, and setting a threshold before knowing
that is a mistake we have made twice this year.

## What we deliberately do not record

- **No IP addresses.** A visitor's IP reaches our server in four different
  headers and all four are dropped. None of the questions we want answered need
  one.
- **No query strings.** Subscriber management links carry a signed token and an
  email address in the URL. Logging the query string would have turned the
  access log into a file of working credentials. Everything after the `?` is
  stripped before anything is written to disk.

Both of those are now checked by tests rather than promised in a comment. The
first version of the filter had one header name in the wrong capitalisation,
which made it silently do nothing; that was caught by running it against a
throwaway server before it went anywhere near the live one.

## The honest limitation

The ticket's headline reason was to find out how much AI-crawler traffic
Cloudflare is currently blocking from the site. A server log cannot answer that:
the block happens at Cloudflare, one hop earlier, so a blocked request never
reaches us to be logged. The nightly summary says so in as many words, because
"AI agents: none" is very easy to misread as "nobody wanted it". Answering that
one properly means turning the block off first, which is a separate decision.

Two of the three questions are now measurable: whether the open dataset is
actually being fetched, and how search crawlers split their attention across our
page types. The second one has been recorded as "unknown" in our own analysis
since August for want of exactly this.
