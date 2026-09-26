#!/usr/bin/env bash
#
# Deploy to the Pi by running the installed deploy agent there, over SSH.
#
#   ./scripts/deploy.sh staging           # after merging to develop and pushing it
#   ./scripts/deploy.sh prod              # ./scripts/release.sh runs this itself
#   ./scripts/deploy.sh prod --force      # redeploy the current tag
#
# THE SESSION THAT SHIPS THE WORK DEPLOYS IT. Nothing on the Pi polls GitHub:
# a merge to develop reaches staging, and a release reaches production, only
# when this runs. The agent it calls (deploy/app-deploy, installed on the Pi as
# ~/.local/bin/<app>-deploy) still decides WHAT to deploy -- origin/develop for
# staging, the newest SIGNED v* tag on origin/main for prod -- so this script
# cannot ship a worktree, a dirty tree or an unpushed commit. It only says when.
#
# Exit code is the agent's: 0 deployed (or already current), 1 failed and
# rolled back, 2 misconfigured, 3 another deploy is running. Anything else is
# the SSH connection itself.
#
# Pi access: pi-deploy (home LAN) first, then pi-remote (Cloudflare Tunnel,
# works anywhere). Set PI_HOST to force one.

set -uo pipefail

ENV_NAME="${1:-}"
FORCE="${2:-}"
case "$ENV_NAME" in
  staging|prod) ;;
  *) echo "usage: scripts/deploy.sh <staging|prod> [--force]" >&2; exit 2 ;;
esac
case "$FORCE" in ""|--force) ;; *) echo "unknown option: $FORCE" >&2; exit 2 ;; esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(grep -E '^APP="' "$REPO/deploy/app-deploy" 2>/dev/null | head -1 | cut -d'"' -f2)"
# Split mid-word: init-project.sh rewrites every whole placeholder word, even half of one.
[ -n "$APP" ] && [ "$APP" != "CHANGE""ME-app" ] \
  || { echo "deploy: APP is not set in deploy/app-deploy" >&2; exit 2; }

# The agent pushes nothing, so an unpushed develop would deploy the OLD commit
# and report success. Catch it here, where the session can still push.
if [ "$ENV_NAME" = staging ] && git -C "$REPO" rev-parse --verify -q develop >/dev/null; then
  git -C "$REPO" fetch -q origin develop 2>/dev/null || true
  if [ -n "$(git -C "$REPO" rev-list origin/develop..develop 2>/dev/null)" ]; then
    echo "deploy: local develop has commits origin/develop lacks — push develop first" >&2
    exit 2
  fi
fi

pick_host() {
  if [ -n "${PI_HOST:-}" ]; then echo "$PI_HOST"; return; fi
  # A LAN miss fails in seconds; that is the wrong route, not a dead Pi.
  if ssh -o ConnectTimeout=5 -o BatchMode=yes pi-deploy true 2>/dev/null; then
    echo pi-deploy
  else
    echo pi-remote
  fi
}
HOST="$(pick_host)"

echo "deploy: ${APP} ${ENV_NAME} via ${HOST}…"
# The first pi-remote call after idle takes 60-90s to negotiate; not a hang.
ssh -o BatchMode=yes "$HOST" "~/.local/bin/${APP}-deploy ${ENV_NAME} ${FORCE}"
code=$?
case "$code" in
  0) echo "deploy: ${APP} ${ENV_NAME} is live and passed its health checks" ;;
  1) echo "deploy: FAILED — the agent rolled back; read its log on the Pi:" >&2
     echo "  ssh ${HOST} tail -50 /mnt/ssd/apps/${APP}$([ "$ENV_NAME" = staging ] && echo -staging)/state/deploy.log" >&2 ;;
  2) echo "deploy: the Pi is not set up for ${ENV_NAME} (docs/DEPLOYMENT.md § Deploy agent)" >&2 ;;
  3) echo "deploy: another deploy holds the lock — wait for it, then re-run" >&2 ;;
  127) echo "deploy: ~/.local/bin/${APP}-deploy is not installed on the Pi (deploy/install-agent.sh)" >&2 ;;
  *) echo "deploy: ssh to ${HOST} failed (exit ${code}); nothing was deployed" >&2 ;;
esac
exit "$code"
