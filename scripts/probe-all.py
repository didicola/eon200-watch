#!/usr/bin/env python3
"""Config-truth probe via CF API (no workers.dev HTTP — WAF-proof).
Exit 0 if every worker has its subdomain enabled and every page project's
latest deployment succeeded. Retired workers vanish automatically because
the roster IS the live API list."""
import sys, os, json, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

CF_TOKEN = os.environ.get("CF_TOKEN", "")
CF_ACC = os.environ.get("CF_ACC", "")
PAGES = ["eon-self", "eon-crypto-blog", "eon-public", "eon-sovereign",
         "eon-promo-agent", "eon-tools-live", "eon-sovereign-cloud", "eon-earner"]

def api(path):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}{path}",
        headers={"Authorization": f"Bearer {CF_TOKEN}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

if not (CF_TOKEN and CF_ACC):
    print("missing CF_TOKEN/CF_ACC env"); sys.exit(2)

# workers: live roster + subdomain flag
j = api("/workers/scripts?per_page=100")
names = [s["id"] for s in (j.get("result") or [])]

def sub_ok(n):
    try:
        r = api(f"/workers/scripts/{n}/subdomain")
        return bool((r.get("result") or {}).get("enabled"))
    except Exception:
        return False

with ThreadPoolExecutor(max_workers=12) as ex:
    flags = list(ex.map(sub_ok, names))
bad = [f"w:{n}" for n, ok in zip(names, flags) if not ok]

# pages: project exists + latest deployment not failed
def page_ok(p):
    try:
        r = api(f"/pages/projects/{p}")
        if not r.get("success"):
            return False
        d = api(f"/pages/projects/{p}/deployments?per_page=1")
        dep = (d.get("result") or [{}])[0]
        state = dep.get("latest_stage", {}).get("status") or dep.get("state") or "unknown"
        return state in ("success", "active")
    except Exception:
        return False

with ThreadPoolExecutor(max_workers=8) as ex:
    pflags = list(ex.map(page_ok, PAGES))
bad += [f"p:{p}" for p, ok in zip(PAGES, pflags) if not ok]

print(f"api-truth: {len(names)} workers, {len(PAGES)} pages; broken: {bad or 'NONE'}")
sys.exit(1 if bad else 0)
