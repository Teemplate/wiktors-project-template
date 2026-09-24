#!/usr/bin/env bash
#
# init-project.sh — turn a copy of this template into a real project.
#
#   ./scripts/init-project.sh my-app
#   ./scripts/init-project.sh my-app --org someone-else
#   ./scripts/init-project.sh my-app --blocks web --target pages   # a static site
#   ./scripts/init-project.sh my-app --blocks api,postgres          # an API, no website
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
# --blocks picks what the project is made of — web, api, worker, postgres —
# (default web,api,postgres) and --target where it runs — pi-compose or pages
# (default pi-compose). Everything else is deleted; see docs/BLOCKS.md.
#
# Does SETUP.md steps 1-4 in one go:
#   1. strips the template's .git            (else your first push lands in it)
#   2. replaces the placeholders             (project-template, CHANGEME*)
#      and keeps only the chosen blocks
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
BLOCKS="web,api,postgres"
TARGET="pi-compose"

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)   usage 0 ;;
    --org)       ORG="${2:?--org needs a value}"; shift 2 ;;
    --no-remote) MAKE_REMOTE=0; shift ;;
    --yes|-y)    ASSUME_YES=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    --blocks)    BLOCKS="${2:?--blocks needs a value, e.g. web,api,postgres}"; shift 2 ;;
    --target)    TARGET="${2:?--target needs a value: pi-compose or pages}"; shift 2 ;;
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

# The block choice is checked BEFORE anything is deleted: a typo in --blocks
# must cost nothing.
if ! block_err="$(python3 scripts/blocks.py set --blocks "$BLOCKS" --target "$TARGET" --dry-run 2>&1 >/dev/null)"; then
  echo "${block_err#blocks: }" >&2
  echo "(see docs/BLOCKS.md, or: python3 scripts/blocks.py status)" >&2
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
if [ "$(basename "$REPO")" = "project-template" ] || [ "$(basename "$REPO")" = "wiktors-project-template" ]; then
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
  blocks       ${BLOCKS//,/, }  on ${TARGET}
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
import json, os, pathlib

app = os.environ["APP"]
skip_dirs = {".git", "node_modules", "dist", ".venv", "__pycache__", "playwright-report", "test-results",
             # local/ is the developer's own gitignored notes about real
             # infrastructure -- not template content, and not ours to rewrite.
             "local"}
# init-project.sh excludes ITSELF for a reason that is not cosmetic: bash reads
# a script incrementally, by byte offset, as it executes. Rewriting this file
# mid-run shifts every later byte and bash resumes in the middle of a different
# line -- observed as "line 157: MSG: No such file or directory" from a heredoc
# that was fine. SETUP.md is excluded because it documents the template and
# cites its real clone URL; substituting there leaves broken instructions.
skip_files = {"SETUP.md", "init-project.sh", "check_agent_context.py", "test_agent_context.py",
              "blocks.py"}
# Longest first: CHANGEME-app-label must not be eaten by CHANGEME-app.
subs = [
    ("<App name>", app),
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

manifest_path = pathlib.Path(".agent-context.json")
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text())
    manifest.update(project=app, is_template=False, development_base="develop")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

for p in sorted(changed):
    print(f"    {p}")
print(f"    ({len(changed)} files)")
PY

# --- 2b. blocks ------------------------------------------------------------
echo "→ keeping blocks: ${BLOCKS//,/, } on ${TARGET}"
python3 scripts/blocks.py set --blocks "$BLOCKS" --target "$TARGET" | sed 's/^/  /'
eval "$(python3 scripts/blocks.py env)"
# Template-only: these prove block combinations of the template, not of a project.
rm -f scripts/check_preset.py scripts/tests/test_blocks.py

# A README describing the template is not a README for this app.
STACK_LINE="$(python3 scripts/blocks.py describe)"
CHECKS="$(python3 scripts/blocks.py checks)"
{
  printf '# %s\n\n%s\n\n' "$APP" "$STACK_LINE"
  if [ "$TARGET" = pages ]; then
    cat <<MSG
Not deployed yet. A push to \`main\` builds and publishes the site through
\`.github/workflows/pages.yml\`, once Pages is enabled for the repository — see
[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md#github-pages).
MSG
  else
    cat <<MSG
Not deployed yet. Set \`PUBLIC_HOST\` in \`.env\` to the hostname you will serve
it on, then follow [SETUP.md](./SETUP.md) step 6 — or
[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md) if the server, tunnel and
reverse proxy do not exist yet.
MSG
  fi
  printf '\n## Run it locally\n\n```bash\ncp .env.example .env          # already done by init-project.sh\ndocker compose up --build\n'
  [ "$HAS_POSTGRES" = 1 ] && printf 'docker compose run --rm migrate python -m app.seed\n'
  printf '```\n\n'
  [ "$HAS_WEB" = 1 ] && printf -- '- frontend http://localhost:5173\n'
  [ "$HAS_API" = 1 ] && printf -- '- backend  http://localhost:8000/api/health\n'
  [ "$HAS_WORKER" = 1 ] && printf -- '- worker   `docker compose logs -f worker`\n'
  printf '\nIf those ports are taken, set `DEV_WEB_PORT` / `DEV_API_PORT` / `DEV_DB_PORT`\nin `.env`.\n'
  printf '\n## Checks\n\n```bash\n%s\n./scripts/e2e.sh              # the whole stack, for real\n```\n' "$CHECKS"
  cat <<'MSG'

## Where things are

| | |
|---|---|
| How to develop here | [AGENTS.md](./AGENTS.md) or [CLAUDE.md](./CLAUDE.md) — same file, one per agent — and [docs/DEVELOPING.md](./docs/DEVELOPING.md) |
| Blocks: what this project is made of, and adding one | [docs/BLOCKS.md](./docs/BLOCKS.md), `python3 scripts/blocks.py status` |
| How it deploys | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) |
MSG
  [ "$HAS_POSTGRES" = 1 ] && printf '| Backups | [docs/BACKUPS.md](./docs/BACKUPS.md) |\n'
  [ "$TARGET" = pi-compose ] && printf '| Remaining setup | [SETUP.md](./SETUP.md) — steps 6 onward (Pi, DNS, Caddy) |\n'
  true
} > README.md
echo "→ wrote a README for ${APP}"

# --- 3. new history --------------------------------------------------------
git init -q -b main
git add -A
python3 scripts/check_agent_context.py
git -c user.email="$(git config --global user.email || echo dev@localhost)" \
    -c user.name="$(git config --global user.name || echo dev)" \
    commit -q -m "chore: initial commit from project-template

Scaffolded with scripts/init-project.sh, blocks: ${BLOCKS//,/, } on ${TARGET}.
Carries the template's development environment for those blocks: disposable
e2e stack, block-gated CI, instructions for both Codex and Claude Code, and the
target's deploy path."
git branch develop
echo "→ git history started: main + develop"

# --- 5. local env (before the remote, so a failed push still leaves it) -----
if [ ! -f .env ]; then
  cp .env.example .env
  if ! grep -q '^SECRET_KEY=' .env; then
    echo "→ wrote .env (these blocks use no SECRET_KEY)"
  elif command -v openssl >/dev/null 2>&1; then
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
  1. docker compose up --build$( [ "$HAS_POSTGRES" = 1 ] && echo "      # then: docker compose run --rm migrate python -m app.seed")
  2. ./scripts/e2e.sh               # proves the whole stack on a clean tree
  3. grep -rn CHANGEME .            # should find nothing outside SETUP.md
MSG
if [ "$TARGET" = pages ]; then cat <<MSG
  4. Enable Pages with a workflow source:
       gh api -X POST repos/${ORG:-<owner>}/${APP}/pages -f build_type=workflow
     then push to main (./scripts/release.sh). docs/DEPLOYMENT.md § GitHub Pages
MSG
else cat <<MSG
  4. SETUP.md steps 6+              # .env on the Pi, DNS, Caddy block, deploy
  5. Choose ONE deploy model: deploy/ (recommended) or .github/workflows/deploy.yml
MSG
fi
cat <<MSG

You are on branch develop. Feature branches fork from here.
MSG
