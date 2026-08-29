#!/usr/bin/env python3
"""Fast read-only status probe (no heal). Exit 0 if ALL 200."""
import sys, urllib.request, urllib.parse
GEN = ["api-anthropic","api-cloudflare","api-google","api-groq","api-huggingface","api-kimi","api-mistral","api-openai","api-openrouter","api-telegram-eon","api-togeth-ai","api-zai","deepseek","eon-ai-chat","eon-auto-deployer","eon-auto-learner","eon-cloud-backup-alpha","eon-cloud-backup-bravo","eon-cloud-backup-charlie","eon-config","eon-cron-trigger","eon-crypto-indicator","eon-data-fusion","eon-deep-ping","eon-deploy-prod","eon-edu-copilot","eon-exporter","eon-fleet-hub","eon-fleet-hub-v3","eon-fleet-syncer","eon-ghost-miner","eon-gitops","eon-glue","eon-heartbeat-farm","eon-inbox","eon-indexer","eon-job-runner","eon-lgpt","eon-metadata","eon-miner-1","eon-miner-10","eon-miner-11","eon-miner-12","eon-miner-13","eon-miner-2","eon-miner-3","eon-miner-4","eon-miner-5","eon-miner-6","eon-miner-7","eon-miner-8","eon-miner-9","eon-mirror","eon-monitor-hub","eon-page-blog","eon-page-portfolio","eon-prompt","eon-proxy-swarm","eon-rag-2","eon-readlogs","eon-scan-engine","eon-scraper-ai","eon-ssg-blog","eon-tools","eon-tools-v2","eon-tools-v3","eon-vision","home-cloud-relay","llm-probe","memory-cache","probe-fetch-test","eon-edge-orchestrator"]
PAGES = ["eon-self","eon-crypto-blog","eon-public","eon-sovereign","eon-promo-agent","eon-tools-live","eon-sovereign-cloud","eon-earner"]
def code(u):
    try:
        r = urllib.request.urlopen(u, timeout=12)
        return r.getcode()
    except Exception:
        return 0
bad = []
for w in GEN:
    c = code(f"https://{w}.eon-sovereign.workers.dev/")
    if c != 200: bad.append(f"{w}({c})")
for p in PAGES:
    c = code(f"https://{p}.pages.dev/")
    if c != 200: bad.append(f"{p}({c})")
print(f"probed {len(GEN)} workers + {len(PAGES)} pages; broken: {bad or 'NONE'}")
sys.exit(1 if bad else 0)
