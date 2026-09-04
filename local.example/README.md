# `local/` — your own infrastructure notes

This directory is the **tracked template**. Copy it to `local/`, which is
gitignored, and put your real values there:

```bash
cp -r local.example local
```

## Why this exists

The docs in this repository are deliberately generic — `example.com`,
`<pi-lan-ip>`, `<your-org>` — so that anyone can use the template. But *you* have
one specific server, with one domain and one set of SSH aliases, and retyping
them (or re-deriving them from shell history six months later) is the actual
friction.

`local/` is where those live. It is the answer to "what is the real hostname
again?" without that answer being in a public repository.

## The rules

1. **`local/` is gitignored and this repository is public.** Never move a file
   out of it "just for a moment". CI fails the build if anything under `local/`
   is ever tracked — see the `no local/ files tracked` step in `ci.yml`.
2. **No secrets, still.** Passwords, tokens, private keys and `SECRET_KEY`
   belong in `.env` (also gitignored) or a password manager. This folder is for
   *addresses and layout* — the things that are awkward to look up, not the
   things that grant access. A gitignore protects against the wrong commit; it
   does not protect against a stolen laptop.
3. **It does not exist in a fresh worktree.** Gitignored files never do — the
   same trap as `.env` and `node_modules`. Symlink it when you need it:
   ```bash
   ln -s ../../../local local
   ```
4. **Keep it current.** A stale note that says an app is live somewhere it is
   not is worse than no note, because it will be believed.

## What goes where

| File | Holds |
|---|---|
| `infrastructure.md` | The server, domain, network, SSH aliases, tunnel, paths |
| `deployments.md` | Which apps are live, where, and how each one redeploys |

Add more files if you have more to record. Nothing reads these
programmatically — they are for you, and for an agent session that has been
pointed at them by `AGENTS.md`/`CLAUDE.md`.
