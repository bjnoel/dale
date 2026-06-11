# treestock.com.au subscriber admin view — setup runbook

A read-only dashboard of subscribers and what they're subscribed to, at
`https://treestock.com.au/admin`. Gated by Cloudflare Access at the edge and by
CF Access JWT validation at the origin (so a direct-to-origin request can't
bypass the gate). View only: it never writes any data.

Code: `tools/scrapers/admin_view.py` (data + render), the `/admin` route and
`verify_cf_access` in `tools/scrapers/subscribe_server.py`, the `/admin` handles
in `infrastructure/Caddyfile`.

## One-time setup (after the branch lands on `main`)

### 1. Cloudflare Zero Trust (Benedict, in the Cloudflare dashboard)
1. Zero Trust → Settings → Custom Pages / General: set a **Team domain** if not
   already set, e.g. `bjnoel` → `https://bjnoel.cloudflareaccess.com`.
2. Access → Applications → **Add an application** → **Self-hosted**.
   - Application name: `treestock admin`
   - Session duration: your preference (e.g. 24h)
   - Public hostname: domain `treestock.com.au`, path `admin`
3. Add a policy: Action **Allow**, Include → **Emails** → `b@bjnoel.com`
   (add any other allowed admins). Login methods: One-time PIN (email) and/or
   Google.
4. Save. Open the application's **Overview** and copy the **Application Audience
   (AUD) Tag**.

### 2. Server config (`ssh dale-server`)
Add the two values to the env the subscribe server already reads:

```
# /opt/dale/secrets/app.env  (append; do not commit)
CF_ACCESS_TEAM_DOMAIN=https://bjnoel.cloudflareaccess.com
CF_ACCESS_AUD=<the AUD tag copied above>
```

Install the JWT dependency (one-time):

```
pip3 install pyjwt cryptography
```

### 3. Deploy code + Caddy
```
# from the repo on your laptop, once merged to main:
tools/deploy.sh                       # rsyncs tools/scrapers/ to /opt/dale/scrapers/

# on the server: update Caddy and restart the subscribe server
ssh dale-server
sudo cp /opt/dale/repo/infrastructure/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
systemctl list-units | grep subscribe   # find the unit name (sibling: bee-subscribe-server)
sudo systemctl restart <subscribe-server-unit>
```

## Verify
1. Fresh browser → `https://treestock.com.au/admin` → redirected to Cloudflare
   Access login → after auth, the dashboard renders with live counts/tables.
2. Bypass check (should be blocked):
   `curl -sk https://178.104.20.9/admin -H 'Host: treestock.com.au' -o /dev/null -w '%{http_code}\n'`
   → **403** (no CF Access JWT). If you get 200, the origin JWT check isn't
   active — confirm PyJWT is installed and the two CF_ACCESS_* vars are set.

## Notes
- The page shows subscriber emails (PII). Keep it `noindex`, don't link it from
  the public site.
- The route **fails closed**: if PyJWT is missing or the CF_ACCESS_* vars are
  unset, `/admin` returns 403 rather than leaking data.
- To change who can see it, edit the Cloudflare Access policy (no redeploy).
