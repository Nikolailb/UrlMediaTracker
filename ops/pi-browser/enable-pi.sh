#!/usr/bin/env bash
set -euo pipefail

# REQ-015: activate the already running, loopback-only browser service for the
# FreeWebNovel site adapter. Run as root on the Pi after a verified backup.
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
if systemctl is-active --quiet keihub-update.service; then
    echo 'KeiHub updater is active; retry when it finishes' >&2
    exit 1
fi

project=/srv/keihub/sources/tracker
browser=/srv/keihub/sources/tracker-browser
compose="$project/compose.yaml"
[[ -f "$compose" && -f "$browser/compose.yaml" && -f "$browser/public_egress_proxy.py" ]] || {
    echo 'Tracker or browser host files are missing' >&2
    exit 1
}

backup_dir="/srv/keihub/rollback/host-browser-$(date -u +%Y%m%dT%H%M%SZ)"
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
needle = '      COVER_DIR: /data/covers\n'
assert text.count(needle) == 1, 'Unexpected tracker Compose environment layout'
assert 'FLARESOLVERR_URL:' not in text and 'FLARESOLVERR_ALLOWED_HOSTS:' not in text, 'Browser already configured'
text = text.replace(needle, needle +
    '      FLARESOLVERR_URL: http://127.0.0.1:8191\n' +
    '      FLARESOLVERR_ALLOWED_HOSTS: freewebnovel.com\n')
path.write_text(text)
PY

docker compose -f "$compose" config --quiet
docker compose -f "$browser/compose.yaml" config --quiet
docker compose -f "$compose" up -d --no-build --force-recreate app

ready=false
for _ in {1..30}; do
    if curl --fail --silent --show-error --output /dev/null --max-time 3 http://127.0.0.1:8761/health; then
        ready=true
        break
    fi
    sleep 2
done
[[ "$ready" == true ]] || { echo 'Tracker health failed after browser activation' >&2; false; }

trap - ERR
if [[ "$timer_was_active" == true ]]; then systemctl start keihub-update.timer; fi
echo "FreeWebNovel browser option enabled; old tracker Compose saved at $backup_dir"
