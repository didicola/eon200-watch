#!/usr/bin/env python3
"""Dynamic roster probe (no heal). Exit 0 if ALL current workers+pages answer 200.
Roster = live CF API list, so retired workers can never haunt this probe again."""
import sys, os, json, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

CF_TOKEN = os.environ.get("CF_TOKEN", "")
CF_ACC = os.environ.get("CF_ACC", "")
PAGES = ["eon-self", "eon-crypto-blog", "eon-public", "eon-sovereign",
         "eon-promo-agent", "eon-tools-live", "eon-sovereign-cloud", "eon-earner"]

def api_names():
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}/workers/scripts?per_page=100",
        headers={"Authorization": f"Bearer {CF_TOKEN}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read())
    return [s["id"] for s in (j.get("result") or [])]

def code(u):
    try:
        return urllib.request.urlopen(u, timeout=12).getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0

if not (CF_TOKEN and CF_ACC):
    print("missing CF_TOKEN/CF_ACC env"); sys.exit(2)

names = api_names()
targets = [(f"https://{w}.eon-sovereign.workers.dev/", f"w:{w}") for w in names] + \
          [(f"https://{p}.pages.dev/", f"p:{p}") for p in PAGES]
with ThreadPoolExecutor(max_workers=20) as ex:
    codes = list(ex.map(lambda t: code(t[0]), targets))
bad = [f"{tag}({c})" for (u, tag), c in zip(targets, codes) if c != 200]
print(f"probed {len(names)} workers + {len(PAGES)} pages; broken: {bad or 'NONE'}")
sys.exit(1 if bad else 0)
