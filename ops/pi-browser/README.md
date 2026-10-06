# Pi browser option (REQ-015)

This optional service is initially enabled on the KeiHub Pi for `freewebnovel.com`.
The tracker first makes one guarded direct request. Its FreeWebNovel site adapter
uses FlareSolverr only after a challenge, connection failure, or timeout. The
generic ToC checker can use the same transport only for a separately allowlisted
host. URL probing and the general site diagnostic never use it.

`compose.yaml` pins the ARM64-tested images. FlareSolverr has only an internal
Docker network; the dual-homed `public_egress_proxy.py` is its sole web route.
The proxy rejects non-public DNS results and pins the outbound connection to a
validated IP. Its FlareSolverr API gateway binds only to Pi loopback port 8191.
The browser does not have a LAN or internet-facing API port.

## Install or reapply

1. Inspect the live tracker database path and row count. Verify a fresh KeiHub
   encrypted backup before changing host files. Check that no updater is active.
2. Copy this directory's `compose.yaml` and
   `backend/devtools/public_egress_proxy.py` to
   `/srv/keihub/sources/tracker-browser/` as `compose.yaml` and
   `public_egress_proxy.py`. Use root-owned, mode 0644 files.
3. Run `sudo docker compose -f /srv/keihub/sources/tracker-browser/compose.yaml
   config --quiet`, then `sudo docker compose -f
   /srv/keihub/sources/tracker-browser/compose.yaml up -d`.
4. Verify the browser can fetch a FreeWebNovel series, has no direct external
   route, rejects private proxy destinations, and binds `8191` to
   `127.0.0.1` only. Run `sudo bash enable-pi.sh`. It backs up the original
   tracker Compose in `/srv/keihub/rollback/host-browser-<timestamp>/`, adds
   the two opt-in environment values, recreates the app, and checks readiness.
5. Check one read-only FreeWebNovel adapter result from the running tracker.
   Confirm the chapter URL belongs to the requested series. Check RAM and swap
   during requests. Take another verified encrypted snapshot after activation.

The Pi currently reports that Docker memory limits are unsupported by its
kernel, even though the Compose file declares them. The application permits
only one browser request at a time. Do not expand the allowlist or add parallel
browser workers without another resource check. The upstream FlareSolverr
project warns that each browser request launches Chromium and uses substantial
memory.

## Comix rendered chapter rows (REQ-016)

The Comix adapter reads latest and first chapter links from the directly
reachable series metadata. A preferred group's link needs rendered chapter
rows. A bounded Pi browser request returned HTTP 200 with 20 chapter rows and
20 group links; afterward about 3 GiB RAM was available and swap remained
unused. After the REQ-016 image passes CI and deploys, run a fresh verified
backup, copy `allow-comix-pi.sh` to the Pi, and run it as root. It changes only
the exact existing allowlist to `freewebnovel.com,comix.to`, saves the previous
Compose file under `/srv/keihub/rollback/`, recreates the app, and checks
health. The direct metadata result remains usable if group lookup fails.
Restore the saved Compose file and recreate the app to reverse this host change.

## Roll back

Install the saved `compose.yaml` from the reported `host-browser-<timestamp>`
directory over `/srv/keihub/sources/tracker/compose.yaml`, then run
`sudo docker compose -f /srv/keihub/sources/tracker/compose.yaml up -d
--no-build --force-recreate app`. Confirm `/health` through Caddy. Stop the
optional stack with `sudo docker compose -f
/srv/keihub/sources/tracker-browser/compose.yaml down`. No database schema or
entry data is changed by this option.

KeiHub's host-file installer can replace the tracker Compose file. After any
such host update, inspect its environment section and reapply the browser
settings only after checking the restored host configuration and backup.
