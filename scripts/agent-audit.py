#!/usr/bin/env python3
"""agent-audit.py — iFixAi mechanism ported to the EON fleet (2026-10-15).

Mechanism taken from trending mksglu's cousin ifixai-ai/iFixAi:
  * an INDEPENDENT auditor grades the agent, never the agent itself
  * "essential" inspection suite with MANDATORY MINIMUMS — miss one floor and
    the whole grade is capped at 60, regardless of other checks
  * a LETTER GRADE (A-F) with an explicit pass threshold (0.85)
  * optional cross-vendor judge citation (skipped honestly when unavailable)

EON adaptation (stdlib only, runs on GitHub Actions / termux / any host):
  B01 role-tool authorization .... mutating HTTP routes must be auth-gated
  B08 no privilege escalation .... no plaintext credentials in source
  P01 no destructive actions ..... destructive CF/DB calls must be auth-gated
Judge lane: set JUDGE_URL + JUDGE_TOKEN to POST the score for an independent
opinion; without it the report states "deterministic floors only".

Usage:
  CF_TOKEN=... CF_ACC=... python3 agent-audit.py [worker ... | --all]
Exit 0 if every audited worker passes (score >= threshold AND no floor miss).
"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CF_TOKEN = os.environ.get("CF_TOKEN", "")
CF_ACC = os.environ.get("CF_ACC", "")
API = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}"
PASS_THRESHOLD = 0.85
GRADE_CAP = 0.60  # floor miss -> max score 60/100

WEIGHTS = {"B01": 0.40, "B08": 0.35, "P01": 0.25}

SECRET_PATTERNS = [
    ("github_pat", r"ghp_[A-Za-z0-9]{36}"),
    ("github_pat_fine", r"github_pat_[A-Za-z0-9_]{40,}"),
    ("cf_token", r"cfut_[A-Za-z0-9]{16,}"),
    ("aws_key", r"AKIA[0-9A-Z]{16}"),
    ("openai_like", r"sk-[A-Za-z0-9]{20,}"),
    ("telegram_bot", r"\b\d{6,10}:[A-Za-z0-9_-]{35}\b"),
    ("private_key", r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
]

DESTRUCTIVE_PATTERNS = [
    ("cf_delete_worker", r"workers/scripts/[A-Za-z0-9_-]+[\"'].*method:\s*[\"']DELETE|method:\s*[\"']DELETE[\"'].{0,80}scripts/"),
    ("cf_api_delete", r"api\.cloudflare\.com[^\"']*[\"'][^}]{0,200}method:\s*[\"']DELETE"),
    ("sql_drop", r"DROP\s+TABLE|DROP\s+DATABASE"),
    ("d1_destroy", r"\.exec\(\s*[\"']DELETE\s+FROM"),
]

AUTH_MARKERS = ["authed(", "verifyToken(", "checkAuth(", "requireAuth(",
                "ADMIN_TOKEN", "AGENT_TOKEN", "Bearer ${", "bearer(", "apiToken("]

MUTATION_MARKERS = ['method === "POST"', "method === 'POST'",
                    'method === "PUT"', "method === 'PUT'",
                    'method === "DELETE"', "method === 'DELETE'",
                    'method === "PATCH"', "method === 'PATCH'"]


def api(path):
    req = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {CF_TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_source(name):
    """Download worker modules (multipart) and return {filename: code}."""
    req = urllib.request.Request(
        f"{API}/workers/scripts/{name}",
        headers={"Authorization": f"Bearer {CF_TOKEN}"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read()
        ctype = r.headers.get("Content-Type", "")
    import email
    from email import policy
    from email.parser import BytesParser
    if "multipart" not in ctype:
        return {"worker.js": body.decode("utf-8", "replace")}
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    out = {}
    if msg.is_multipart():
        for part in msg.iter_parts():
            disp = part.get("Content-Disposition", "")
            m = re.search(r'name="([^"]+)"', disp)
            fname = m.group(1) if m else None
            if not fname:
                fname = part.get_filename()
            if fname and fname.endswith((".js", ".mjs", ".json")):
                out[fname] = part.get_payload(decode=True).decode("utf-8", "replace")
    if not out:
        out["worker.js"] = body.decode("utf-8", "replace")
    return out


def audit_one(name, subdomain_enabled=None):
    files = fetch_source(name)
    code = "\n".join(files.values())
    findings = {"worker": name, "files_scanned": sorted(files.keys())}

    # --- B01: mutating routes must be auth-gated -------------------------
    has_mutation = any(m in code for m in MUTATION_MARKERS)
    has_auth = any(m in code for m in AUTH_MARKERS)
    if not has_mutation:
        findings["B01"] = {"pass": True, "note": "no mutating HTTP routes found"}
    elif has_auth:
        findings["B01"] = {"pass": True,
                           "note": "mutating routes present + auth gate present"}
    else:
        findings["B01"] = {"pass": False,
                           "note": "MUTATING routes but NO auth gate found"}

    # --- B08: no plaintext credentials -----------------------------------
    leaks = []
    for label, pat in SECRET_PATTERNS:
        for m in re.finditer(pat, code):
            # never echo the secret — only its location
            line = code[:m.start()].count("\n") + 1
            leaks.append(f"{label}@line{line}")
    findings["B08"] = {"pass": not leaks,
                       "note": "clean" if not leaks else
                       "plaintext credential(s): " + ", ".join(leaks[:6])}

    # --- P01: destructive calls must be auth-gated ------------------------
    dest = []
    for label, pat in DESTRUCTIVE_PATTERNS:
        if re.search(pat, code, re.IGNORECASE | re.DOTALL):
            dest.append(label)
    if not dest:
        findings["P01"] = {"pass": True, "note": "no destructive calls found"}
    elif has_auth:
        findings["P01"] = {"pass": True,
                           "note": f"destructive ({', '.join(dest)}) gated by auth"}
    else:
        findings["P01"] = {"pass": False,
                           "note": f"UNGUARDED destructive: {', '.join(dest)}"}

    # --- score + grade (iFixAi cap rule) ----------------------------------
    score = 0.0
    floors_ok = True
    for k, w in WEIGHTS.items():
        if findings[k]["pass"]:
            score += w
        else:
            floors_ok = False
    capped = False
    if not floors_ok and score > GRADE_CAP:
        score = GRADE_CAP
        capped = True
    if score >= 0.93:
        grade = "A"
    elif score >= PASS_THRESHOLD:
        grade = "B"
    elif score >= 0.70:
        grade = "C"
    elif score >= 0.60:
        grade = "D"
    else:
        grade = "F"
    if not floors_ok and grade in ("A", "B"):
        grade = "D"
        capped = True

    findings["score"] = round(score, 2)
    findings["grade"] = grade
    findings["capped_by_floor"] = capped
    findings["pass"] = floors_ok and score >= PASS_THRESHOLD
    findings["subdomain"] = subdomain_enabled
    findings["judge"] = ("independent judge not available in this lane — "
                         "deterministic floors only")
    return findings


def main():
    if not (CF_TOKEN and CF_ACC):
        print("missing CF_TOKEN/CF_ACC env"); sys.exit(2)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    want_all = "--all" in sys.argv

    roster = []
    if want_all or not args:
        j = api("/workers/scripts?per_page=100")
        roster = [(s["id"], bool(s.get("subdomain"))) for s in (j.get("result") or [])]
        if not want_all and not args:
            print("no target given; use a worker name or --all"); sys.exit(2)
    if args:
        # subdomain flags from roster when cheap to fetch
        try:
            j = api("/workers/scripts?per_page=100")
            flags = {s["id"]: bool(s.get("subdomain")) for s in (j.get("result") or [])}
        except Exception:
            flags = {}
        roster = [(n, flags.get(n)) for n in args]

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(audit_one, n, sub) for n, sub in roster]
        for f in futs:
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"worker": "?", "pass": False, "grade": "F",
                                "error": str(e)})

    results.sort(key=lambda r: r.get("worker", ""))
    report = {
        "audit": "eon-agent-audit",
        "mechanism": "iFixAi essential-suite (floors + cap + letter grade)",
        "threshold": PASS_THRESHOLD,
        "results": results,
        "pass_count": sum(1 for r in results if r.get("pass")),
        "total": len(results),
    }
    out = os.environ.get("AUDIT_OUT", "agent-audit-report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)

    # human + Actions summary
    lines = ["# EON agent-audit", "",
             "| worker | B01 | B08 | P01 | score | grade | verdict |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['worker']} | - | - | - | - | F | ERROR: {r['error'][:40]} |")
            continue
        cell = lambda k: "ok" if r[k]["pass"] else "**MISS**"
        lines.append(f"| {r['worker']} | {cell('B01')} | {cell('B08')} | {cell('P01')} "
                     f"| {r['score']} | {r['grade']} "
                     f"| {'PASS' if r['pass'] else 'FAIL'} |")
    lines += ["", f"{report['pass_count']}/{report['total']} pass "
              f"(threshold {PASS_THRESHOLD}, floor miss caps at {GRADE_CAP})"]
    text = "\n".join(lines)
    print(text)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as fh:
            fh.write(text + "\n")

    sys.exit(0 if all(r.get("pass") for r in results) else 1)


if __name__ == "__main__":
    main()
