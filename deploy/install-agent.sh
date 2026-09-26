#!/usr/bin/env bash
#
# install-agent.sh — install the deploy agent ON THE PI.
#
#   ssh pi-remote
#   cd /mnt/ssd/apps/<app>/src && ./deploy/install-agent.sh prod
#   cd /mnt/ssd/apps/<app>-staging/src && ./deploy/install-agent.sh staging
#
# Run this ON THE PI, not from the dev machine. It copies the agent to
# ~/.local/bin/<app>-deploy -- deliberately NOT symlinking it into the checkout,
# because the agent `git reset --hard`s that checkout and would rewrite itself
# mid-run. Re-run it whenever deploy/app-deploy changes (or a block is added
# or removed), so the installed copy learns the new version.
#
# It installs NO timer. Deploys are started by the session that ships the work
# (./scripts/deploy.sh on the dev machine). A Pi set up by an older version of
# this script had a systemd timer polling GitHub every 60s; this removes it.

set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  staging|prod) ;;
  *) echo "usage: install-agent.sh <staging|prod>" >&2; exit 2 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(grep -E '^APP="' "$REPO/deploy/app-deploy" | head -1 | cut -d'"' -f2)"
# The placeholder is spelled in two halves on purpose: init-project.sh replaces
# every literal CHANGEME-app with the project's name, which turned a plain
# comparison into "refuse if APP is the real name" in every generated project.
PLACEHOLDER="CHANGEME""-app"
if [ "$APP" = "$PLACEHOLDER" ]; then
  echo "deploy/app-deploy still says APP=\"$PLACEHOLDER\". Set it first." >&2
  exit 2
fi

PROJECT="$APP"; [ "$ENV_NAME" = staging ] && PROJECT="${APP}-staging"
BASE="/mnt/ssd/apps/${PROJECT}"

mkdir -p ~/.local/bin "${BASE}"/{env,state,backups}
install -m 0755 "$REPO/deploy/app-deploy" ~/.local/bin/"${APP}-deploy"

# Retire the polling timer from the old pull-based model, if this Pi has one.
UNIT_DIR=~/.config/systemd/user
if [ -e "$UNIT_DIR/${APP}-deploy@.timer" ] || [ -e "$UNIT_DIR/${APP}-deploy@.service" ]; then
  for env in staging prod; do
    systemctl --user disable --now "${APP}-deploy@${env}.timer" 2>/dev/null || true
  done
  rm -f "$UNIT_DIR/${APP}-deploy@.timer" "$UNIT_DIR/${APP}-deploy@.service"
  systemctl --user daemon-reload
  echo "Removed the old ${APP}-deploy polling timer: deploys now start from scripts/deploy.sh."
fi

if [ ! -r "${BASE}/env/app.env" ]; then
  echo "!! ${BASE}/env/app.env does not exist yet."
  echo "   Put the real .env there (mode 600); the agent refuses to run without it."
fi

cat <<MSG

Installed ~/.local/bin/${APP}-deploy (${ENV_NAME}).

  deploy:  ./scripts/deploy.sh ${ENV_NAME}          (from the dev machine)
  on Pi:   ~/.local/bin/${APP}-deploy ${ENV_NAME} [--force]
  logs:    tail -f ${BASE}/state/deploy.log

Remaining setup on this machine:
  1. ${BASE}/env/app.env      the real secrets, mode 600
  2. ${BASE}/src              a git clone with a READ-ONLY deploy key
  3. ${BASE}/env/notify.conf  optional: NTFY_TOPIC=... for push alerts
MSG
