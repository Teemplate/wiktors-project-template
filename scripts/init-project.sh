#!/usr/bin/env bash
#
# init-project.sh — turn a copy of this template into a real project.
#
#   ./scripts/init-project.sh my-app
#   ./scripts/init-project.sh my-app --org someone-else
#   ./scripts/init-project.sh my-app --no-remote     # local only, skip GitHub
#   ./scripts/init-project.sh my-app --dry-run       # show, change nothing
#   ./scripts/init-project.sh my-app --yes           # no prompts (CI/scripting)
#
# CAREFUL WITH --yes: it skips the confirmation AND still creates a real GitHub
# repository, which you may not be able to delete (deleting needs the
# delete_repo scope, which a normal `gh auth login` does not grant). Pair it
# with --no-remote for anything experimental. This is not hypothetical -- an
# unwanted repo created exactly this way had to be deleted by hand.
#
# Does SETUP.md steps 1-4 in one go:
#   1. strips the template's .git            (else your first push lands in it)
#   2. replaces the placeholders             (project-template, CHANGEME*)
#   3. git init, first commit, develop branch
#   4. creates the GitHub repo and pushes BOTH branches   <- asks first
#   5. writes .env with a real SECRET_KEY
#
# Steps 6 onward in SETUP.md (Pi deploy, DNS, Caddy) are still manual, and
# should be: they touch shared infrastructure. If you have not set that
# infrastructure up yet, start at docs/INFRASTRUCTURE.md.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Where the template itself lives -- used only in help text, never as the
# destination for the new project.
TEMPLATE_URL="https://github.com/inspizzz/wiktors-project-template.git"

APP=""
# Empty = "whoever `gh` is logged in as", resolved below. --org overrides.
ORG=""
MAKE_REMOTE=1
ASSUME_YES=0
DRY_RUN=0

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)   usage 0 ;;
    --org)       ORG="${2:?--org needs a value}"; shift 2 ;;
    --no-remote) MAKE_REMOTE=0; shift ;;
    --yes|-y)    ASSUME_YES=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    -*)          echo "unknown flag: $1" >&2; usage 2 ;;
    *)           [ -z "$APP" ] || { echo "give exactly one app name" >&2; exit 2; }
                 APP="$1"; shift ;;
  esac
done

[ -n "$APP" ] || { echo "usage: init-project.sh <app-name> [options]" >&2; exit 2; }

# --- who owns the new repo -------------------------------------------------
# Default to the account `gh` is authenticated as, so a fresh clone of this
# template creates repos under YOUR account and not somebody else's.
if [ -z "$ORG" ] && [ "$MAKE_REMOTE" = 1 ]; then
  ORG="$(gh api user -q .login 2>/dev/null || true)"
  if [ -z "$ORG" ]; then
    cat >&2 <<MSG
Cannot tell which GitHub account to create the repo under.

Either log in:            gh auth login
or name the owner:       --org <user-or-org>
or skip GitHub entirely: --no-remote
MSG
    exit 2
  fi
fi

# --- validation ------------------------------------------------------------
# The name becomes a compose project, container prefix, image name and DNS
# label all at once, so it has to satisfy the strictest of those: lowercase
# alphanumerics and dashes, starting with a letter.
if ! printf '%s' "$APP" | grep -qE '^[a-z][a-z0-9-]{1,38}[a-z0-9]$'; then
  cat >&2 <<MSG
"$APP" is not usable as an app name.

It becomes a compose project, container name prefix, image tag and DNS label,
so: lowercase letters, digits and dashes only, starting with a letter, 3-40
characters. No underscores, spaces or capitals.
MSG
  exit 2
fi

if [ "$APP" = "project-template" ]; then
  echo "that is the template's own name — pick the new project's name" >&2
  exit 2
fi

# --- guard: already initialised --------------------------------------------
# Re-running would delete a real project's history. Placeholders gone plus a
# remote that is not the template means this has already been through here.
if [ -d .git ] \
   && ! grep -rq "CHANGEME" --exclude-dir=.git --exclude=SETUP.md --exclude=init-project.sh . 2>/dev/null \
   && ! git remote get-url origin 2>/dev/null | grep -q "project-template"; then
  cat >&2 <<MSG
Refusing to run: this looks like an already-initialised project.

  no CHANGEME placeholders left, and origin is $(git remote get-url origin 2>/dev/null || echo "not the template")

Re-running would delete this project's git history. If you really mean to start
over, remove .git yourself first.
MSG
  exit 2
fi

# --- guard: never rewrite the template itself ------------------------------
# A clone lives in a directory named after the new project; the template lives
# in one named project-template. That is the difference this checks.
if [ "$(basename "$REPO")" = "project-template" ]; then
  cat >&2 <<MSG
Refusing to run: this directory is called "project-template", so it is almost
certainly the template itself rather than a copy of it. Running here would
rewrite the template in place.

Copy it first:

  git clone --depth 1 ${TEMPLATE_URL} ${APP}
  cd ${APP} && ./scripts/init-project.sh ${APP}
MSG
  exit 2
fi

# --- what is about to happen ----------------------------------------------
ORIGIN="$(git remote get-url origin 2>/dev/null || echo "none")"
HAS_GIT=0; [ -d .git ] && HAS_GIT=1

cat <<MSG

  app name     ${APP}
  directory    ${REPO}
  existing git $( [ "$HAS_GIT" = 1 ] && echo "yes (origin: ${ORIGIN}) — WILL BE DELETED" || echo "none" )
  remote       $( [ "$MAKE_REMOTE" = 1 ] && echo "github.com/${ORG}/${APP} (private)" || echo "skipped (--no-remote)" )

This will rewrite files in place, start a new git history, and $( [ "$MAKE_REMOTE" = 1 ] && echo "create a GitHub repository" || echo "leave GitHub alone" ).
MSG

if [ "$DRY_RUN" = 1 ]; then
  echo
  echo "--dry-run: nothing was changed."
  exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
  printf '\nType the app name to confirm: '
  read -r reply
  [ "$reply" = "$APP" ] || { echo "aborted (got '${reply}')"; exit 1; }
fi

# --- 1. strip the template's history ---------------------------------------
if [ "$HAS_GIT" = 1 ]; then
  rm -rf .git
  echo "→ removed the template's .git (origin was ${ORIGIN})"
fi

# --- 2. placeholders -------------------------------------------------------
# SETUP.md is deliberately NOT rewritten: it documents the template and cites
# its real clone URL, so substituting there would leave broken instructions.
echo "→ replacing placeholders"
APP="$APP" python3 - <<'PY'
import os, pathlib

app = os.environ["APP"]
skip_dirs = {".git", "node_modules", "dist", ".venv", "__pycache__", "playwright-report", "test-results"}
# init-project.sh excludes ITSELF for a reason that is not cosmetic: bash reads
# a script incrementally, by byte offset, as it executes. Rewriting this file
# mid-run shifts every later byte and bash resumes in the middle of a different
# line -- observed as "line 157: MSG: No such file or directory" from a heredoc
# that was fine. SETUP.md is excluded because it documents the template and
# cites its real clone URL; substituting there leaves broken instructions.
skip_files = {"SETUP.md", "init-project.sh"}
# Longest first: CHANGEME-app-label must not be eaten by CHANGEME-app.
subs = [
    ("CHANGEME-app-label", f"{app}-runner"),
    ("CHANGEME-app", app),
    ("CHANGEME", app),
    ("project-template", app),
]

changed = []
for path in pathlib.Path(".").rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    if any(part in skip_dirs for part in path.parts) or path.name in skip_files:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        continue
    new = text
    for old, repl in subs:
        new = new.replace(old, repl)
    if new != text:
        path.write_text(new, encoding="utf-8")
        changed.append(str(path))

for p in sorted(changed):
    print(f"    {p}")
print(f"    ({len(changed)} files)")
PY

# A README describing the template is not a README for this app.
cat > README.md <<MSG
# ${APP}

$(printf '%s' "${APP}" | tr '[:lower:]-' '[:upper:] ' | cut -c1)$(printf '%s' "${APP}" | cut -c2- | tr '-' ' ') — a Docker Compose app on the Raspberry Pi 5, behind the shared
Caddy and Cloudflare Tunnel. Vite/React frontend, FastAPI/Postgres backend.

Not deployed yet. Set \`PUBLIC_HOST\` in \`.env\` to the hostname you will serve
it on, then follow [SETUP.md](./SETUP.md) step 6 — or
[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md) if the server, tunnel and
reverse proxy do not exist yet.

## Run it locally

\`\`\`bash
cp .env.example .env          # already done by init-project.sh
docker compose up --build
docker compose exec backend python -m app.seed
\`\`\`

- frontend http://localhost:5173
- backend  http://localhost:8000/api/health

If those ports are taken, set \`DEV_WEB_PORT\` / \`DEV_API_PORT\` / \`DEV_DB_PORT\`
in \`.env\`.

## Checks

\`\`\`bash
cd backend  && pytest
cd frontend && npm run typecheck && npm test && npm run build
./scripts/e2e.sh              # the whole stack, for real
\`\`\`

## Where things are

| | |
|---|---|
| How to develop here | [CLAUDE.md](./CLAUDE.md), [docs/DEVELOPING.md](./docs/DEVELOPING.md) |
| How it deploys | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) |
| Backups | [docs/BACKUPS.md](./docs/BACKUPS.md) |
| Remaining setup | [SETUP.md](./SETUP.md) — steps 6 onward (Pi, DNS, Caddy) |
MSG
echo "→ wrote a README for ${APP}"

# --- 3. new history --------------------------------------------------------
git init -q -b main
git add -A
git -c user.email="$(git config --global user.email || echo dev@localhost)" \
    -c user.name="$(git config --global user.name || echo dev)" \
    commit -q -m "chore: initial commit from project-template

Scaffolded with scripts/init-project.sh. Carries the template's development
environment: seed script, disposable e2e stack, alembic migrations, 7-job CI,
and a pull-based signed-tag deploy agent."
git branch develop
echo "→ git history started: main + develop"

# --- 5. local env (before the remote, so a failed push still leaves it) -----
if [ ! -f .env ]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
    # `|` as the delimiter: a hex secret cannot contain it, unlike `/`.
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${secret}|" .env
    echo "→ wrote .env with a freshly generated SECRET_KEY"
  else
    echo "→ wrote .env — openssl absent, SO SET SECRET_KEY BY HAND"
  fi
fi

# --- 4. the remote ---------------------------------------------------------
if [ "$MAKE_REMOTE" = 1 ]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "!! gh is not installed; skipping the remote. Create it later with:"
    echo "   gh repo create ${ORG}/${APP} --private --source=. --remote=origin"
  elif ! gh auth status >/dev/null 2>&1; then
    echo "!! gh is not authenticated (run: gh auth login); skipping the remote."
  else
    echo "→ creating github.com/${ORG}/${APP} (private)"
    gh repo create "${ORG}/${APP}" --private --source=. --remote=origin
    git push -q -u origin main develop
    # develop as default so PRs and auto-created agent branches target it.
    gh repo edit "${ORG}/${APP}" --default-branch develop
    echo "→ pushed main + develop; default branch is develop"
  fi
fi

git switch -q develop

cat <<MSG

Done. ${APP} is a project.

Next, in order (SETUP.md has the detail):
  1. docker compose up --build      # then: docker compose exec backend python -m app.seed
  2. ./scripts/e2e.sh               # proves the whole stack on a clean tree
  3. grep -rn CHANGEME .            # should find nothing outside SETUP.md
  4. SETUP.md steps 6+              # .env on the Pi, DNS, Caddy block, deploy
  5. Choose ONE deploy model: deploy/ (recommended) or .github/workflows/deploy.yml

You are on branch develop. Feature branches fork from here.
MSG
