#!/usr/bin/env bash
#
# install-agent.sh — install the pull-based deploy agent ON THE PI.
#
#   ssh pi-remote
#   cd /mnt/ssd/apps/<app>/src && ./deploy/install-agent.sh staging
#   cd /mnt/ssd/apps/<app>/src && ./deploy/install-agent.sh prod
#
# Run this ON THE PI, not from the dev machine. It copies the agent to
# ~/.local/bin -- deliberately NOT symlinking it into the checkout, so that
# merging a branch cannot change the agent that is about to deploy it.

set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  staging|prod) ;;
  *) echo "usage: install-agent.sh <staging|prod>" >&2; exit 2 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(grep -E '^APP="' "$REPO/deploy/app-deploy" | head -1 | cut -d'"' -f2)"
if [ "$APP" = "CHANGEME-app" ]; then
  echo "deploy/app-deploy still says APP=\"CHANGEME-app\". Set it first." >&2
  exit 2
fi

PROJECT="$APP"; [ "$ENV_NAME" = staging ] && PROJECT="${APP}-staging"
BASE="/mnt/ssd/apps/${PROJECT}"

mkdir -p ~/.local/bin ~/.config/systemd/user "${BASE}"/{env,state,backups}

install -m 0755 "$REPO/deploy/app-deploy" ~/.local/bin/"${APP}-deploy"
# The unit template is per-app, so two apps on one Pi do not collide.
sed "s|%h/.local/bin/app-deploy|%h/.local/bin/${APP}-deploy|; s|^Description=Deploy agent|Description=${APP} deploy agent|" \
  "$REPO/deploy/app-deploy@.service" > ~/.config/systemd/user/"${APP}-deploy@.service"
sed "s|Unit=app-deploy@|Unit=${APP}-deploy@|; s|^Description=Poll GitHub for deploys|Description=Poll GitHub for ${APP} deploys|" \
  "$REPO/deploy/app-deploy@.timer" > ~/.config/systemd/user/"${APP}-deploy@.timer"

if [ ! -r "${BASE}/env/app.env" ]; then
  echo "!! ${BASE}/env/app.env does not exist yet."
  echo "   Put the real .env there (mode 600) before enabling the timer;"
  echo "   the agent refuses to run without it."
fi

systemctl --user daemon-reload
systemctl --user enable --now "${APP}-deploy@${ENV_NAME}.timer"

# Without lingering, the user manager stops at logout and the timer dies with
# it -- the deploy then silently never runs again until the next login.
loginctl enable-linger "$USER" 2>/dev/null || \
  echo "note: could not enable-linger; run 'sudo loginctl enable-linger $USER'"

cat <<MSG

Installed ${APP}-deploy for ${ENV_NAME}.

  status:  systemctl --user status ${APP}-deploy@${ENV_NAME}.timer
  run now: systemctl --user start  ${APP}-deploy@${ENV_NAME}.service
  logs:    tail -f ${BASE}/state/deploy.log

Remaining setup on this machine:
  1. ${BASE}/env/app.env      the real secrets, mode 600
  2. ${BASE}/src              a git clone with a READ-ONLY deploy key
  3. ${BASE}/env/notify.conf  optional: NTFY_TOPIC=... for push alerts
MSG
