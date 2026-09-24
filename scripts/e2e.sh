#!/usr/bin/env bash
#
# scripts/e2e.sh — bring up a disposable stack, migrate it, seed it, run
# Playwright against it, and tear it down.
#
#   ./scripts/e2e.sh              # everything
#   ./scripts/e2e.sh --keep       # leave the stack running to poke at
#   ./scripts/e2e.sh --ui         # Playwright's UI mode (implies --keep)
#   ./scripts/e2e.sh smoke.spec   # any extra args go to `playwright test`
#
# It exercises only the blocks this project has (blocks.json): the seed and
# row-count checks need postgres, the /api proxy check needs web and api, the
# browser tests need web, and a worker must reach a healthy heartbeat.
#
# Nothing here needs a secret. That is deliberate: CI runs this exact script,
# and CI here is secretless. If a spec ever needs a real credential,
# make it SKIP without one rather than fail -- see the pattern below.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# HAS_WEB, HAS_API, HAS_WORKER, HAS_POSTGRES, DATA_ROUTE — see scripts/blocks.py.
eval "$(python3 scripts/blocks.py env)"

# Derive the compose project from the directory name, so two copies of this
# template on one machine cannot fight over container names.
PROJECT="$(basename "$REPO" | tr '[:upper:] ' '[:lower:]-')-e2e"
COMPOSE=(docker compose -f compose.e2e.yml -p "$PROJECT" --env-file .env.e2e)

KEEP=0
PW_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;;
    --ui)   KEEP=1; PW_ARGS+=(--ui) ;;
    *)      PW_ARGS+=("$arg") ;;
  esac
done

WEB_PORT="${E2E_WEB_PORT:-5273}"
API_PORT="${E2E_API_PORT:-8273}"
WEB_URL="http://localhost:${WEB_PORT}"
API_URL="http://localhost:${API_PORT}"

# Fail now, with a sentence a human can act on, rather than 90 seconds into a
# build with an inscrutable docker networking error.
PORTS=()
[ "$HAS_WEB" = 1 ] && PORTS+=("web:${WEB_PORT}")
[ "$HAS_API" = 1 ] && PORTS+=("api:${API_PORT}")
for pair in "${PORTS[@]}"; do
  name="${pair%%:*}"; port="${pair##*:}"
  if ss -ltn 2>/dev/null | grep -q ":${port} "; then
    echo "port ${port} (${name}) is already in use." >&2
    echo "Set E2E_WEB_PORT / E2E_API_PORT to something free and re-run." >&2
    exit 1
  fi
done

cleanup() {
  # BACK TO THE REPO ROOT FIRST. The test run ends with `cd frontend`, so by the
  # time this trap fires the cwd is not where compose.e2e.yml lives -- and every
  # command below uses a repo-relative path. Without this the teardown prints
  # "tearing down", fails to find the compose file, has the error swallowed by
  # `|| true`, and leaves the whole stack running. It looks like it worked.
  cd "$REPO" || return
  if [ "$KEEP" = "1" ]; then
    echo "→ stack left up: web ${WEB_URL}, api ${API_URL}"
    echo "  tear down with: docker compose -f compose.e2e.yml -p ${PROJECT} down -v"
    return
  fi
  echo "→ tearing down"
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f .env.e2e
}
trap cleanup EXIT

# --- environment -----------------------------------------------------------
# Written fresh every run and deleted on teardown. Nothing in it is secret: it
# is a throwaway database on a tmpfs that dies with the stack.
cat > .env.e2e <<EOF
E2E_PROJECT=${PROJECT}
E2E_WEB_PORT=${WEB_PORT}
E2E_API_PORT=${API_PORT}

APP_NAME=e2e
SECRET_KEY=e2e-secret-not-used-anywhere-real

POSTGRES_USER=e2e
POSTGRES_PASSWORD=e2e-not-a-secret
POSTGRES_DB=e2e
DATABASE_URL=postgresql+asyncpg://e2e:e2e-not-a-secret@db:5432/e2e

# No third-party credentials. Any spec that needs one must skip without it, so
# that this file never has to hold a real key.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
chmod 600 .env.e2e

# --- stack -----------------------------------------------------------------
echo "→ building and starting the stack (project ${PROJECT})"
"${COMPOSE[@]}" up -d --build

wait_healthy() {   # a service with no port: trust its Docker healthcheck
  local svc="$1" id
  id="$("${COMPOSE[@]}" ps -q "$svc")"
  for i in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null)" = healthy ] && return 0
    sleep 2
  done
  echo "$svc never became healthy" >&2
  "${COMPOSE[@]}" logs --tail 40 "$svc" >&2
  exit 1
}

if [ "$HAS_API" = 1 ]; then
echo "→ waiting for the api"
for i in $(seq 1 60); do
  curl -fsS -m 3 "${API_URL}/api/health" >/dev/null 2>&1 && break
  if [ "$i" = 60 ]; then
    echo "api never came up" >&2
    "${COMPOSE[@]}" logs --tail 40 >&2   # every service: migrate may be the culprit
    exit 1
  fi
  sleep 2
done

fi

if [ "$HAS_POSTGRES" = 1 ]; then
  echo "→ seeding"
  # `migrate` is the postgres block's own one-shot, so this works whichever
  # Python service the project has.
  "${COMPOSE[@]}" run --rm -T migrate python -m app.seed
fi

if [ "$HAS_WORKER" = 1 ]; then
  echo "→ waiting for the worker's heartbeat"
  wait_healthy worker
  echo "→ worker healthy"
fi

if [ "$HAS_WEB" = 1 ]; then
echo "→ waiting for the web front end"
for i in $(seq 1 60); do
  curl -fsS -m 3 -o /dev/null "${WEB_URL}/" && break
  if [ "$i" = 60 ]; then
    echo "web never came up" >&2
    "${COMPOSE[@]}" logs --tail 40 web >&2
    exit 1
  fi
  sleep 2
done

fi

if [ "$HAS_API" = 1 ] && [ "$HAS_POSTGRES" = 1 ]; then
# A seeded database is a PRECONDITION, not an assertion. Without this check
# every UI test would pass vacuously against an empty list.
COUNT=$(curl -fsS "${API_URL}/api/items" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')
if [ "$COUNT" -lt 3 ]; then
  echo "expected a seeded database, got ${COUNT} item(s)" >&2
  exit 1
fi
echo "→ ${COUNT} items seeded"
fi

if [ "$HAS_WEB" = 1 ] && [ "$HAS_API" = 1 ]; then
# Prove the nginx /api proxy specifically. If this returns HTML, the SPA
# fallback is swallowing /api/* and every browser test would fail with an
# opaque JSON parse error instead of naming the real cause.
CT=$(curl -fsS -o /dev/null -w '%{content_type}' "${WEB_URL}/api/health")
case "$CT" in
  application/json*) echo "→ /api proxied correctly through nginx" ;;
  *) echo "web /api/health returned '${CT}', not JSON — the nginx /api proxy is not working" >&2; exit 1 ;;
esac
fi

# --- tests -----------------------------------------------------------------
# Browser tests need a page. Without the web block, the checks above were the
# whole suite.
if [ "$HAS_WEB" != 1 ]; then
  echo "→ no web block: stack checks passed, no browser tests to run"
  exit 0
fi

cd frontend
# Check for the PACKAGE, not the directory: a named-volume mount can leave an
# empty, root-owned node_modules behind, so "does the directory exist" is true
# while nothing is installed and npm cannot write there either.
if [ ! -d node_modules/@playwright/test ]; then
  if [ -d node_modules ] && [ ! -w node_modules ]; then
    cat >&2 <<'MSG'
frontend/node_modules exists but is not writable -- it is an empty root-owned
mount point left by a compose named volume, not a real install.

  sudo rm -rf frontend/node_modules && (cd frontend && npm ci)

then re-run. (CI is unaffected: it starts from a clean checkout.)
MSG
    exit 1
  fi
  echo "→ installing frontend dependencies"
  npm ci --no-audit --no-fund
fi
npx playwright install --with-deps chromium >/dev/null 2>&1 || npx playwright install chromium

E2E_BASE_URL="$WEB_URL" E2E_API_URL="$API_URL" \
  npx playwright test "${PW_ARGS[@]}"
