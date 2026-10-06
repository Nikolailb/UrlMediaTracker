#!/usr/bin/env bash
set -euo pipefail

# REQ-015/016: allow one guarded rendered Comix lookup for preferred-group
# links after the Comix adapter has been deployed and tested. Run as root.
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
if systemctl is-active --quiet keihub-update.service; then
    echo 'KeiHub updater is active; retry when it finishes' >&2
    exit 1
fi

compose=/srv/keihub/sources/tracker/compose.yaml
browser=/srv/keihub/sources/tracker-browser/compose.yaml
[[ -f "$compose" && -f "$browser" ]] || { echo 'Host Compose files are missing' >&2; exit 1; }
python3 - <<'PY'
from datetime import datetime, timedelta, timezone
import json

backup = json.load(open('/srv/keihub/operations/backup.json', encoding='utf-8'))
ended = datetime.fromisoformat(backup['ended_at'])
assert backup['outcome'] == 'success', 'A verified backup is required'
assert datetime.now(timezone.utc) - ended < timedelta(hours=2), 'Backup is too old'
PY

backup_dir="/srv/keihub/rollback/host-comix-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 0700 "$backup_dir"
cp -a "$compose" "$backup_dir/compose.yaml"

timer_was_active=false
if systemctl is-active --quiet keihub-update.timer; then
    timer_was_active=true
    systemctl stop keihub-update.timer
fi

restore() {
    trap - ERR
    install -m 0644 "$backup_dir/compose.yaml" "$compose"
    docker compose -f "$compose" up -d --no-build --force-recreate app || true
    if [[ "$timer_was_active" == true ]]; then systemctl start keihub-update.timer; fi
}
trap restore ERR

python3 - "$compose" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
before = 'FLARESOLVERR_ALLOWED_HOSTS: freewebnovel.com'
assert text.count(before) == 1, 'Unexpected browser allowlist'
assert 'FLARESOLVERR_URL: http://127.0.0.1:8191' in text, 'Guarded browser endpoint is missing'
path.write_text(text.replace(before, before + ',comix.to'))
PY

docker compose -f "$compose" config --quiet
docker compose -f "$browser" config --quiet
docker compose -f "$compose" up -d --no-build --force-recreate app

ready=false
for _ in {1..30}; do
    if curl --fail --silent --show-error --output /dev/null --max-time 3 http://127.0.0.1:8761/health; then
        ready=true
        break
    fi
    sleep 2
done
[[ "$ready" == true ]] || { echo 'Tracker health failed after Comix activation' >&2; false; }

trap - ERR
if [[ "$timer_was_active" == true ]]; then systemctl start keihub-update.timer; fi
echo "Comix browser lookup enabled; old Compose saved at $backup_dir"
