# What is deployed, and how

> Copy of the template. Keep the real version in `local/` — never commit it.

This replaces the "which server was that on again?" problem. One row per app,
and **update it when you deploy**, not later. A stale entry is worse than an
empty one: it gets believed.

## Live

| App | URL | Target | Compose project | Deploy model | Data |
|---|---|---|---|---|---|
| `<app>` | `https://<app>.<example.com>` | `<server>` | `<app>` | deploy agent (`scripts/deploy.sh`) / manual | `<path>` |

## Redeploy

```bash
# Deploy agent: the session that ships runs it; nothing on the server polls.
./scripts/release.sh vX.Y.Z --yes   # signed tag, push, then deploys prod
./scripts/deploy.sh staging         # after pushing develop

# Manual, from the primary checkout on main — never from a worktree:
docker --context <lan-alias> compose -f compose.deploy.yml -p <app> up -d --build
```

## Health

Check an `/api/*` route, not a page — a page returns 200 with a dead backend.

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<app>.<example.com>/api/health
```

**Status codes that are correctly not 200.** Record them here, per app, so a
correct response is never read as an outage:

| App | Path | Code | Why it is correct |
|---|---|---|---|
| `<app>` | `/` | `<e.g. 307>` | `<e.g. redirect to /login>` |

## Not deployed / retired

| App | State | Note |
|---|---|---|
| `<app>` | `<local only / retired <date>>` | `<what happened to its data>` |
