# Infrastructure — the one-time setup

Everything else in this repo assumes a server that already has a shared Caddy, a
Cloudflare Tunnel and an SSH route. **This document builds that.** You do it once
per server, not once per app.

If you already have that setup, skip to [SETUP.md](../SETUP.md).

```
                 Cloudflare edge (terminates TLS)
                            │
                   ┌────────┴────────┐   no inbound ports on your router;
                   │  Cloudflare      │   cloudflared dials OUT and holds
                   │  Tunnel          │   the connection open
                   └────────┬────────┘
                            │
  ┌─────────────────────────┼─────────────────────────────────┐
  │ the Pi                  │                                 │
  │              ┌──────────▼──────────┐                      │
  │              │ cloudflared         │  docker network web  │
  │              └──────────┬──────────┘                      │
  │              ┌──────────▼──────────┐                      │
  │              │ caddy (shared)      │  routes by Host      │
  │              └──┬───────────────┬──┘                      │
  │       ┌─────────▼──────┐ ┌──────▼─────────┐               │
  │       │ app-a-frontend │ │ app-b-frontend │  one compose  │
  │       └────────────────┘ └────────────────┘  stack each   │
  └───────────────────────────────────────────────────────────┘
```

Two properties fall out of this, and both matter:

- **Nothing is exposed on your router.** No port forwarding, no DDNS, no public
  SSH. `cloudflared` makes an outbound connection and everything rides it.
- **TLS is Cloudflare's problem.** Caddy never sees a certificate, which is why
  every site block in the Caddyfile is written `http://`.

Placeholders used below: `example.com` is your domain, `<pi-lan-ip>` is the Pi's
address on your LAN, `pi` is the Linux user on the Pi.

---

## 0. What you need first

| | |
|---|---|
| A server | Raspberry Pi 5 (4 GB works, 8 GB is comfortable). Any always-on arm64 or x86-64 Linux box does — nothing here is Pi-specific except the arm64 build notes |
| Storage | An SSD. Building Docker images on an SD card is painfully slow and wears it out |
| A domain | On **Cloudflare**, nameservers already pointed at them. Free plan is fine |
| A Cloudflare account | With **Zero Trust** enabled — free for up to 50 users |
| On your laptop | `docker`, `git`, `ssh`, and [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) |

> **Free-plan limit worth knowing now.** Cloudflare does not proxy **wildcard**
> DNS records below the Business plan. That is why the tunnel below uses a
> catch-all *ingress* rule and one ordinary DNS record per app, rather than a
> single `*.example.com`. The per-app record is one command.

---

## 1. The Pi: OS, storage, Docker

**Use the 64-bit OS.** Raspberry Pi OS *Lite* (64-bit) is the right image — no
desktop. A 32-bit install cannot run the arm64 images this template builds, and
the failure appears late and confusingly, as exec-format errors inside the
container rather than at install time.

```bash
uname -m          # must print aarch64
```

### Mount the SSD at `/mnt/ssd`

Every path in this repo (`/mnt/ssd/apps/<app>/`) assumes it.

```bash
lsblk -f                                    # find the device and its UUID
sudo mkfs.ext4 /dev/sda1                    # ONLY if it is a blank disk
sudo mkdir -p /mnt/ssd
echo 'UUID=<uuid> /mnt/ssd ext4 defaults,noatime,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a
df -h /mnt/ssd                              # confirm before continuing
```

`nofail` is deliberate: without it, a Pi that boots with the SSD unplugged drops
to an emergency shell instead of coming up, and you have no remote access to fix
it.

### Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker                               # or log out and back in
docker run --rm hello-world
```

### Move Docker's data onto the SSD

Images and build cache are the bulk of the disk use, and the SD card is small.

```bash
sudo systemctl stop docker
sudo mkdir -p /mnt/ssd/docker
printf '{\n  "data-root": "/mnt/ssd/docker"\n}\n' | sudo tee /etc/docker/daemon.json
sudo rsync -aP /var/lib/docker/ /mnt/ssd/docker/
sudo systemctl start docker
docker info | grep 'Docker Root Dir'        # -> /mnt/ssd/docker
```

### Give it swap

A 4-core Pi running a Vite build alongside two Postgres instances will hit the
OOM killer. The default 100 MB swap is not enough.

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

---

## 2. SSH from your laptop (`pi-deploy`)

The template's docs and `docker context` both refer to a host alias, never a raw
address. Define it:

```bash
ssh-copy-id pi@<pi-lan-ip>          # if you have not already
```

In `~/.ssh/config` **on your laptop**:

```sshconfig
Host pi-deploy
    HostName <pi-lan-ip>
    User pi
    IdentityFile ~/.ssh/id_ed25519
```

```bash
ssh pi-deploy 'hostname && docker --version'
```

`pi-remote` — the same Pi from outside your house — comes in [step 7](#7-ssh-from-anywhere-pi-remote),
once the tunnel exists.

---

## 3. The shared `web` network

`compose.deploy.yml` declares this network `external: true`, meaning *"this
already exists, I am only joining it."* If it does not exist, every deploy fails
immediately with `network web declared as external, but could not be found`.

```bash
ssh pi-deploy 'docker network create web'
```

One network, created once, shared by Caddy, cloudflared and every app.

---

## 4. The Cloudflare Tunnel

Run these **on the Pi**.

```bash
sudo mkdir -p /srv/edge/cloudflared && sudo chown -R "$USER" /srv/edge
curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/
```

### Authenticate and create the tunnel

```bash
cloudflared tunnel login
```

This prints a URL. Open it on any machine, pick your domain, and it writes
`~/.cloudflared/cert.pem` on the Pi. That certificate authorises *creating*
tunnels and DNS records; it is not what the tunnel runs on.

```bash
cloudflared tunnel create home
```

Note the **tunnel UUID** it prints, and the credentials file it wrote to
`~/.cloudflared/<UUID>.json`. That JSON *is* the tunnel's identity — treat it
like a password, and never commit it.

```bash
cp ~/.cloudflared/<UUID>.json /srv/edge/cloudflared/
chmod 600 /srv/edge/cloudflared/<UUID>.json
```

### The ingress config

```bash
cat > /srv/edge/cloudflared/config.yml <<'EOF'
tunnel: <UUID>
credentials-file: /etc/cloudflared/<UUID>.json

ingress:
  # SSH, so the Pi is reachable from outside the LAN (step 7).
  # host.docker.internal resolves to the Pi itself — cloudflared runs in a
  # container and sshd does not, so "localhost" would be the wrong host.
  - hostname: ssh.example.com
    service: ssh://host.docker.internal:22

  # Catch-all: everything else goes to the shared Caddy, which routes on the
  # Host header. This is why adding an app needs no tunnel change — only a DNS
  # record and a Caddy block.
  - service: http://caddy:80
EOF
```

> **Order matters.** cloudflared takes the *first* matching rule, and a rule
> with no `hostname` matches everything. Anything below the catch-all is dead
> config — put specific hostnames above it, always.

Substitute the real UUID in both places:

```bash
UUID=$(cloudflared tunnel list --output json \
  | python3 -c 'import json,sys; print(next(t["id"] for t in json.load(sys.stdin) if t["name"]=="home"))')
sed -i "s/<UUID>/$UUID/g" /srv/edge/cloudflared/config.yml
grep -E 'tunnel:|credentials-file:' /srv/edge/cloudflared/config.yml
```

Both lines must now show a UUID, and `/srv/edge/cloudflared/$UUID.json` must
exist — a typo here surfaces later as a tunnel that starts and never connects.

---

## 5. The shared Caddy

One Caddy for the whole server. Apps never run their own, and never publish
ports — Caddy reaches them by container name on the `web` network.

```bash
sudo mkdir -p /srv/caddy && sudo chown "$USER" /srv/caddy
cat > /srv/caddy/Caddyfile <<'EOF'
# One block per app. Written http:// on purpose: Cloudflare terminates TLS at
# its edge, and Caddy has no public port on which to answer an ACME challenge,
# so https:// here makes Caddy try — and fail — to get its own certificate.
#
# reverse_proxy targets a CONTAINER NAME on the `web` network, not a port on
# the host.

# http://myapp.example.com {
#     reverse_proxy myapp-frontend:5173
# }

# Anything not matched above. Without this, an unrouted hostname gets a bare
# Caddy 404 and you cannot tell it apart from a broken app.
:80 {
    respond "no app is routed to this hostname" 404
}
EOF
```

### Bring the edge up

```bash
cat > /srv/edge/compose.yml <<'EOF'
# The shared edge: TLS-terminated traffic in via cloudflared, routed by Caddy.
# Deliberately separate from any app stack — restarting an app must never take
# every other site down with it.
name: edge

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    volumes:
      - /srv/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data          # keep: certs and OCSP staples
      - caddy-config:/config
    networks: [web]

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate --config /etc/cloudflared/config.yml run
    volumes:
      - /srv/edge/cloudflared:/etc/cloudflared:ro
    extra_hosts:
      # Lets the ssh:// ingress rule reach the Pi's own sshd.
      - "host.docker.internal:host-gateway"
    networks: [web]

networks:
  web:
    external: true

volumes:
  caddy-data:
  caddy-config:
EOF

docker compose -f /srv/edge/compose.yml up -d
docker compose -f /srv/edge/compose.yml logs cloudflared | tail -20
```

You are looking for `Registered tunnel connection` — usually four of them, to
different Cloudflare data centres.

---

## 6. Prove the edge works before deploying anything

Do this now, with a throwaway container. Debugging the tunnel and a half-built
app at the same time is how an afternoon disappears.

```bash
docker run -d --name edge-test --network web nginx:alpine
```

Add the block and route the DNS:

```bash
printf '\nhttp://test.example.com {\n    reverse_proxy edge-test:80\n}\n' >> /srv/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile

cloudflared tunnel route dns home test.example.com
```

`tunnel route dns` creates the proxied CNAME to `<UUID>.cfargotunnel.com` for
you — this is the per-app DNS step, and the reason you do not need the
Cloudflare dashboard.

```bash
curl -sI https://test.example.com | head -1     # HTTP/2 200
```

Then clean up — leaving it running is a stray public endpoint:

```bash
docker rm -f edge-test
sed -i '/test.example.com/,+2d' /srv/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

**If it did not return 200,** work outward in this order — each step rules out
everything before it:

| Check | Means |
|---|---|
| `docker exec caddy wget -qO- http://edge-test:80` | Caddy → app. Fails: not on the `web` network, or wrong container name |
| `docker compose -f /srv/edge/compose.yml logs cloudflared` | Tunnel is connected at all |
| `dig +short test.example.com` | Should be Cloudflare IPs, not `cfargotunnel.com` |
| `curl -sI https://test.example.com` returns **502** | Tunnel and Caddy are alive; the *origin* is not — this is the good failure, and the one the deploy agent's edge check looks for |
| returns **530** / **1033** | cloudflared is not connected — restart it and read its logs |

---

## 7. SSH from anywhere (`pi-remote`)

The ingress rule from step 4 already exposes SSH. **Do not stop here** — right
now `ssh.example.com` is an unauthenticated door onto your network. Put
Cloudflare Access in front of it.

### Protect it with Access

In the Cloudflare **Zero Trust** dashboard → *Access* → *Applications* → *Add an
application* → **Self-hosted**:

- Application domain: `ssh.example.com`
- Policy: *Allow*, with an **Emails** rule listing your own address

Then route the hostname and check the policy exists **before** relying on it:

```bash
cloudflared tunnel route dns home ssh.example.com
curl -sI https://ssh.example.com | head -1      # 302 to the Access login = protected
```

A `200` here means Access is **not** in front of it. Fix that before moving on.

### The client side

On your laptop, add to `~/.ssh/config`:

```sshconfig
Host pi-remote
    HostName ssh.example.com
    User pi
    ProxyCommand cloudflared access ssh --hostname %h
    IdentityFile ~/.ssh/id_ed25519
```

```bash
ssh pi-remote hostname
```

The first connection opens a browser for the Access login and caches a token.
**The first call after an idle period takes 60–90 seconds** to negotiate — that
is normal, not a hang, and the rest of these docs say so repeatedly because it
looks exactly like a dead Pi.

---

## 8. Docker contexts

Both docs and both deploy models drive Docker over SSH rather than exposing the
Docker socket — which should never be published to a network.

```bash
docker context create pi-deploy --docker host=ssh://pi-deploy
docker context create pi-remote --docker host=ssh://pi-remote
docker --context pi-deploy info | head -5
```

Use `pi-deploy` at home, `pi-remote` outside. Off the LAN, `pi-deploy` fails
instantly with `Network is unreachable` — that is the wrong route, not a dead
server.

---

## 9. Signing keys — required for production deploys

`deploy/app-deploy` refuses to deploy a production tag unless `git verify-tag`
passes. **Skip this and production silently deploys nothing**, logging only
`tag ... is not signed` while staging keeps working — a genuinely confusing
failure. SSH signing is the least painful route.

On your **laptop**:

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global tag.gpgsign true
```

On the **Pi**, tell git which keys to trust:

```bash
mkdir -p /mnt/ssd/apps
cat > /mnt/ssd/apps/allowed_signers <<'EOF'
you@example.com namespaces="git" ssh-ed25519 AAAA...your-public-key...
EOF
git config --global gpg.ssh.allowedSignersFile /mnt/ssd/apps/allowed_signers
```

Paste the contents of your `~/.ssh/id_ed25519.pub` where indicated — the email
must match the one in your signed tags.

Verify the whole chain before you rely on it:

```bash
# laptop
git tag -s v0.0.1-signing-test -m "signing test" && git push origin v0.0.1-signing-test
# Pi, inside the clone
git fetch --tags && git verify-tag v0.0.1-signing-test && echo "SIGNING OK"
# then
git tag -d v0.0.1-signing-test && git push origin :v0.0.1-signing-test
```

---

## 10. A read-only deploy key per app

The pull-based agent clones over SSH with a key scoped to **one** repository, so
a compromised Pi cannot write to your GitHub account.

On the **Pi**, per app:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_myapp -N "" -C "myapp deploy key (pi)"
cat ~/.ssh/deploy_myapp.pub
```

Add that public key at *GitHub → the repo → Settings → Deploy keys → Add* —
and **leave "Allow write access" unchecked.**

Then in `~/.ssh/config` **on the Pi**:

```sshconfig
Host github-myapp
    HostName github.com
    User git
    IdentityFile ~/.ssh/deploy_myapp
    IdentitiesOnly yes
```

`IdentitiesOnly yes` matters: with several deploy keys, ssh otherwise offers
them in turn and GitHub accepts the first valid one — which may be a different
repository's key, and the clone fails with a misleading permission error.

```bash
git clone git@github-myapp:<your-org>/myapp.git /mnt/ssd/apps/myapp/src
```

That path is what `deploy/install-agent.sh` expects.

---

## Done — what you have now

- [ ] `uname -m` on the Pi prints `aarch64`
- [ ] `/mnt/ssd` mounted, in `/etc/fstab` with `nofail`
- [ ] Docker installed, data-root on the SSD, swap raised
- [ ] `docker network create web` done
- [ ] `cloudflared` and `caddy` both up, tunnel showing registered connections
- [ ] A test hostname returned **200 through the edge**, then was cleaned up
- [ ] `ssh pi-deploy` works on the LAN; `ssh pi-remote` works off it
- [ ] `ssh.example.com` returns a **302 to Access**, not a 200
- [ ] `docker --context pi-deploy info` works from the laptop
- [ ] A signed test tag verified **on the Pi**
- [ ] Deploy key added read-only (per app, when you add one)

## Adding each app, from here

The one-time work is done. Every app after this is three steps, and
[SETUP.md](../SETUP.md) step 6 walks them:

1. `cloudflared tunnel route dns home myapp.example.com`
2. A `http://myapp.example.com { reverse_proxy myapp-frontend:5173 }` block in
   `/srv/caddy/Caddyfile`, then `docker exec caddy caddy reload --config /etc/caddy/Caddyfile`
3. Deploy

**Do 1 and 2 before the first deploy.** The deploy's edge health check tests the
public URL, so deploying first fails the check even though the build and the
containers are perfectly fine.
