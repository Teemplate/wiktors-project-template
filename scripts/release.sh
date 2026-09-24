#!/usr/bin/env bash
#
# Cut a release: develop -> release/vX.Y.Z -> main (tagged) -> back into develop.
#
#   ./scripts/release.sh v1.2.0 --dry-run   # print every command, run none
#   ./scripts/release.sh v1.2.0             # the whole chain, one confirmation
#   ./scripts/release.sh v1.2.0 --yes       # no prompt (for a script calling this)
#
# WHAT HAPPENS WHEN IT PUSHES main DEPENDS ON WHETHER YOU OPTED IN.
# .github/workflows/deploy.yml only runs when the repository variable
# SELF_HOSTED_DEPLOY is "true" AND a self-hosted runner exists. Until then a push
# to main is just a push, and the deploy is still the manual compose command in
# docs/DEPLOYMENT.md. The script tells you which case you are in at the end
# rather than assuming — claiming "deployed" when nothing ran is the one lie a
# release script must not tell.
#
# RUN IT FROM THE PRIMARY CHECKOUT. It checks out three branches, and a worktree
# cannot check out a branch the primary checkout already holds — but the real
# reason is the one in AGENTS.md/CLAUDE.md: a worktree has no .env, so anything
# that builds from one ships empty ${VAR} interpolation.
#
# Why a script at all, when it is only six commands: both ways the chain goes
# wrong are quiet. Merging a feature branch straight to main leaves main with
# commits develop has never seen, so the NEXT release conflicts; forgetting the
# final merge back leaves the release commit only on main, to be re-merged next
# time. Neither surfaces until weeks later, so this does the whole chain or none.

set -euo pipefail

VERSION="${1:-}"
DRY_RUN=0
ASSUME_YES=0
for arg in "${@:2}"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes|-y)  ASSUME_YES=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

die() { echo "release: $*" >&2; exit 1; }

[[ -n "$VERSION" ]] || die "usage: scripts/release.sh vX.Y.Z [--dry-run] [--yes]"
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must look like v1.2.0, got '$VERSION'"

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  would run: %s\n' "$*"
  else
    printf '  + %s\n' "$*"
    "$@"
  fi
}

# --- preconditions: all cheap, all things that have actually gone wrong ---

git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

if [[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]]; then
  die "run this from the primary checkout, not a worktree (see AGENTS.md)"
fi

[[ -z "$(git status --porcelain)" ]] || die "working tree is dirty — commit or discard first"

git rev-parse --verify --quiet "refs/tags/$VERSION" >/dev/null \
  && die "tag $VERSION already exists"

echo "release: fetching…"
git fetch origin --tags --quiet

for b in main develop; do
  git rev-parse --verify --quiet "origin/$b" >/dev/null || die "origin/$b does not exist"
done

# Everything released must already be on develop. If main has commits develop
# lacks, a hotfix was never merged back: merging main into this release drags
# them in unreviewed, and not merging loses them at the next release. A human
# has to decide which, so stop.
BEHIND=$(git rev-list --count "origin/develop..origin/main")
if [[ "$BEHIND" -ne 0 ]]; then
  echo "release: origin/main has $BEHIND commit(s) origin/develop does not:" >&2
  git log --oneline "origin/develop..origin/main" >&2
  die "merge main back into develop first (the hotfix rule), then re-run"
fi

AHEAD=$(git rev-list --count "origin/main..origin/develop")
[[ "$AHEAD" -ne 0 ]] || die "origin/develop has nothing origin/main lacks — nothing to release"

# Where this project runs (blocks.json): the pages target publishes itself.
TARGET="$(python3 -c 'import json; print(json.load(open("blocks.json"))["target"])' 2>/dev/null || echo pi-compose)"

# Is the runner actually going to pick this up? Best-effort: gh may be missing or
# unauthenticated, in which case say so rather than guess either way.
DEPLOY_STATE="unknown"
if command -v gh >/dev/null 2>&1; then
  if VAL=$(gh variable list --json name,value -q '.[] | select(.name=="SELF_HOSTED_DEPLOY") | .value' 2>/dev/null); then
    [[ "$VAL" == "true" ]] && DEPLOY_STATE="on" || DEPLOY_STATE="off"
  fi
fi

echo
echo "release: $VERSION"
echo "  $AHEAD commit(s) from develop will be tagged and pushed to main:"
git log --oneline --no-decorate "origin/main..origin/develop" | sed 's/^/    /'
echo
if [ "$TARGET" = pages ]; then
  DEPLOY_STATE="pages"
fi
case "$DEPLOY_STATE" in
  pages) echo "  pages target — the push to main publishes the site (.github/workflows/pages.yml)." ;;
  on)  echo "  SELF_HOSTED_DEPLOY=true — the push to main WILL rebuild production." ;;
  off) echo "  SELF_HOSTED_DEPLOY is not true — pushing main will NOT deploy."
       echo "  You will still need the manual compose command afterwards." ;;
  *)   echo "  Could not read SELF_HOSTED_DEPLOY (no gh, or not authenticated)."
       echo "  If it is set, this push deploys; if not, deploy manually afterwards." ;;
esac
echo

if [[ $DRY_RUN -eq 0 && $ASSUME_YES -eq 0 ]]; then
  read -r -p "release $VERSION? type the version to confirm: " reply
  [[ "$reply" == "$VERSION" ]] || die "aborted (got '$reply')"
fi

START_BRANCH=$(git rev-parse --abbrev-ref HEAD)
# Leave the checkout where we found it if anything fails, so a broken release
# does not strand the shared primary checkout on a half-made release branch.
cleanup() {
  local code=$?
  if [[ $code -ne 0 && $DRY_RUN -eq 0 ]]; then
    echo "release: FAILED — returning to $START_BRANCH" >&2
    git checkout --quiet "$START_BRANCH" 2>/dev/null || true
  fi
  exit $code
}
trap cleanup EXIT

echo "release: develop -> release/$VERSION"
run git checkout develop
run git pull --ff-only origin develop
run git checkout -b "release/$VERSION"

echo "release: -> main"
run git checkout main
run git pull --ff-only origin main
run git merge --no-ff "release/$VERSION" -m "Merge branch 'release/$VERSION' into main"
run git tag -a "$VERSION" -m "$VERSION"

echo "release: pushing main"
run git push origin main
run git push origin "$VERSION"

# Merge MAIN back, not the release branch. Merging the release branch is a no-op
# whenever it is identical to develop, which leaves main's merge commit off
# develop forever — and the BEHIND check at the top of the next release then
# reads that as an unmerged hotfix and refuses to run. Merging main is what
# keeps `origin/develop..origin/main` empty between releases, which is the
# invariant this whole script depends on. (Caught by actually running it.)
echo "release: merging main back into develop"
run git checkout develop
run git merge --no-ff main -m "Merge main back into develop after $VERSION"
run git push origin develop
run git branch -d "release/$VERSION"

echo
if [[ $DRY_RUN -eq 1 ]]; then
  echo "release: dry run only — nothing was changed or pushed."
  exit 0
fi

echo "release: $VERSION is on main."
if [ "$TARGET" = pages ]; then
  echo "The pages target deploys itself: .github/workflows/pages.yml publishes main."
  echo "  gh run watch \$(gh run list --workflow=pages.yml -L1 --json databaseId -q '.[0].databaseId')"
  echo "It is skipped until Pages is enabled for the repository (docs/DEPLOYMENT.md § GitHub Pages)."
  echo "Then load the site itself — the workflow going green is not the page serving."
  exit 0
fi
case "$DEPLOY_STATE" in
  on)
    echo "The runner should be building now:"
    echo "  gh run watch \$(gh run list --workflow=deploy.yml -L1 --json databaseId -q '.[0].databaseId')"
    ;;
  *)
    echo "Now deploy it — from the PRIMARY CHECKOUT, which has .env:"
    echo "  docker --context pi-deploy compose -f compose.deploy.yml -p CHANGEME up -d --build"
    echo "(-p is not optional; a different project name builds a second image set"
    echo " and then collides on container_name. If pi-deploy fails instantly you"
    echo " are off the LAN — use pi-remote, do not conclude the Pi is down.)"
    ;;
esac
echo
echo "Then verify an /api/* route, not just a page — a page returns 200 even when"
echo "the container cannot reach the backend at all. (No api block? Check what the"
echo "project has: the page, or the worker's heartbeat.) Codes that are correctly"
echo "not 200 for this app are recorded in AGENTS.md under 'Health checks'."
