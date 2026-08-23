# My infrastructure

> Copy of the template. Replace every `<...>` with your real value, delete what
> does not apply, and keep it in `local/` — never commit it.
> The generic version of all of this is [docs/INFRASTRUCTURE.md](../docs/INFRASTRUCTURE.md).

## The server

| | |
|---|---|
| Hardware | `<e.g. Raspberry Pi 5, 8 GB>` |
| OS | `<e.g. Raspberry Pi OS Lite 64-bit (aarch64)>` |
| Login user | `<pi-user>` |
| LAN address | `<pi-lan-ip>` |
| Storage | `<e.g. 1 TB SSD at /mnt/ssd, UUID ...>` |
| Docker data-root | `<e.g. /mnt/ssd/docker>` |

## Domain and DNS

| | |
|---|---|
| Domain | `<example.com>` |
| Registrar / DNS | `<e.g. Cloudflare, free plan>` |
| Apps are served at | `<app>.<example.com>` |

## Cloudflare Tunnel

| | |
|---|---|
| Tunnel name | `<tunnel-name>` |
| Tunnel UUID | `<uuid>` |
| Credentials file | `<e.g. /srv/edge/cloudflared/<uuid>.json>` — on the server only |
| Ingress config | `<e.g. /srv/edge/cloudflared/config.yml>` |
| Edge compose stack | `<e.g. /srv/edge/compose.yml>` |

Add a hostname:

```bash
cloudflared tunnel route dns <tunnel-name> <app>.<example.com>
```

## Reverse proxy

| | |
|---|---|
| Caddyfile | `<e.g. /srv/caddy/Caddyfile>` |
| Shared network | `<e.g. web>` |
| Reload | `docker exec caddy caddy reload --config /etc/caddy/Caddyfile` |

Per-app block — `http://`, never `https://`:

```
http://<app>.<example.com> {
    reverse_proxy <app>-frontend:5173
}
```

## SSH

| Alias | Route | Works |
|---|---|---|
| `<lan-alias>` | LAN `<pi-lan-ip>` | home network only |
| `<remote-alias>` | Cloudflare Access → `<ssh.example.com>` | anywhere |

`~/.ssh/config` on this machine:

```sshconfig
Host <lan-alias>
    HostName <pi-lan-ip>
    User <pi-user>
    IdentityFile ~/.ssh/id_ed25519

Host <remote-alias>
    HostName <ssh.example.com>
    User <pi-user>
    ProxyCommand cloudflared access ssh --hostname %h
    IdentityFile ~/.ssh/id_ed25519
```

The first call after an idle period takes 60–90s to negotiate. That is normal.

## Docker contexts

```bash
docker context create <lan-alias>    --docker host=ssh://<lan-alias>
docker context create <remote-alias> --docker host=ssh://<remote-alias>
```

## Paths on the server

| Path | Holds |
|---|---|
| `<e.g. /mnt/ssd/apps/<app>/>` | Per-app root |
| `<.../env/app.env>` | The real `.env`, mode 600 |
| `<.../src>` | Deploy agent's clone (read-only deploy key) |
| `<.../backups>` | Pre-deploy `pg_dump`s |
| `<.../postgres-data>` | Bind-mounted database |

## Tag signing

| | |
|---|---|
| Signing key | `<e.g. ~/.ssh/id_ed25519.pub>` |
| Signing email | `<you@example.com>` |
| Allowed signers on server | `<e.g. /mnt/ssd/apps/allowed_signers>` |

Production refuses an unsigned tag, so this must work before a release:

```bash
git tag -s vX.Y.Z -m "..." && git push origin vX.Y.Z
```

## GitHub

| | |
|---|---|
| Owner / org | `<your-org>` |
| New repos default to | `<private or public>` |
