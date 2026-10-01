#!/bin/bash
# Export dataset v2 (all documents, NDJSON) → Parrot v2/export/ + Google Drive gdrive:sanity_backups/hw-for-ai-lab/
# Usage: ./export.sh [label]
set -euo pipefail
cd "$(dirname "$0")"
T=$(python3 -c "import sys;sys.path.insert(0,'..');from secrets_env import tok;print(tok('SANITY_WRITE_TOKEN'))")
f="export/v2_$(date +%F_%H%M)${1:+_$1}.ndjson"
mkdir -p export
curl -sf -H "Authorization: Bearer $T" "https://onwa0wvs.api.sanity.io/v2025-09-01/data/export/v2" -o "$f"
n=$(grep -vc '"_id":"_\.' "$f" || true)
echo "exported $n documents → $f"
rclone copy "$f" gdrive:sanity_backups/hw-for-ai-lab/ && echo "copied to gdrive:sanity_backups/hw-for-ai-lab/$(basename "$f")"
