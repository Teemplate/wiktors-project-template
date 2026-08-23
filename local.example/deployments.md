# What is deployed, and how

> Copy of the template. Keep the real version in `local/` — never commit it.

This replaces the "which server was that on again?" problem. One row per app,
and **update it when you deploy**, not later. A stale entry is worse than an
empty one: it gets believed.

## Live

| App | URL | Target | Compose project | Deploy model | Data |
|---|---|---|---|---|---|
| `<app>` | `https://<app>.<example.com>` | `<server>` | `<app>` | signed-tag agent / runner / manual | `<path>` |

## Redeploy

```bash
# Pull-based agent: push a signed tag, the server picks it up within 60s.
git tag -s vX.Y.Z -m "..." && git push origin vX.Y.Z

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
