"""One place to get Search Console credentials.

gsc_analysis.py and gsc_submit.py each built their own credential off Benedict's
personal Google account, the first by copying the second (its docstring still
says "from gsc_submit.py pattern"). That is the fork this package exists to
prevent, and it had a cost beyond duplication: a personal token reaches all 13
properties on his account, including aoi.com.au, zombal.com and rfcarchives.org.au,
none of which are Dale's. The service account reaches the 9 that are.

Both moved to the service account on 2026-08-24, once Benedict granted it Full on
sc-domain:treesmith.app and the remaining question was whether a service account
could do the two things the token was kept for. Measured against the live API:

    URL Inspection, webmasters.readonly   200  verdict PASS
    URL Inspection, webmasters            200  verdict PASS
    Sitemaps list,  webmasters            200  variety.xml, 2801 URLs submitted

So inspection needs no write scope, and `write=True` is reserved for the sitemap
PUT in gsc_submit.py.

The one trap, because it reads as a permissions failure and is not: the OAuth
path sent `x-goog-user-project: dale-490702`, and sending that header with a
service-account token fails with

    403 Caller does not have required permission to use project dale-490702.
    Grant the caller the roles/serviceusage.serviceUsageConsumer role...

which invites you to start granting IAM roles. A service account bills its own
project and must simply not send the header. auth_headers() is the reason there
is no longer a place to put one by hand.
"""

from google.oauth2 import service_account
from google.auth.transport.requests import Request

CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"

READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/webmasters"


def gsc_credentials(write=False, credentials_path=CREDENTIALS_PATH):
    """Return refreshed service-account credentials for Search Console.

    Read-only by default. Pass write=True only for calls that change state on
    Google's side, which today is submitting a sitemap.
    """
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=[WRITE_SCOPE if write else READONLY_SCOPE]
    )
    creds.refresh(Request())
    return creds


def refresh_credentials(creds):
    """Re-mint the access token on a long run.

    Kept here so callers never need google.auth.transport directly, which is how
    the credential-building code spread across two files in the first place.
    """
    creds.refresh(Request())
    return creds


def auth_headers(creds, extra=None):
    """Headers for a raw requests call against the Search Console REST API.

    Deliberately no x-goog-user-project: see the module docstring.
    """
    headers = {"Authorization": f"Bearer {creds.token}"}
    if extra:
        headers.update(extra)
    return headers
