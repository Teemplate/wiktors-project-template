#!/usr/bin/env python3
"""blocks.py — choose, prune, add and wire this project's blocks.

    python3 scripts/blocks.py status                  # what this project is made of
    python3 scripts/blocks.py set --blocks web,api --target pi-compose [--dry-run]
    python3 scripts/blocks.py add worker --from ../<template checkout> [--dry-run]
    python3 scripts/blocks.py sync                    # regenerate the root compose files
    python3 scripts/blocks.py check                   # manifest, files and compose agree
    python3 scripts/blocks.py env [--github]          # flags for shell scripts / CI
    python3 scripts/blocks.py checks                  # the check commands for these blocks
    python3 scripts/blocks.py describe                # one line: the stack

`set` only removes (it is what init-project.sh --blocks runs); `add` copies a
block's files back in from a template checkout. docs/BLOCKS.md is the contract
and blocks.json the manifest. Standard library only: this runs in CI, on the Pi
and on a fresh clone with nothing installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "blocks.json"

# Compose include order: dependencies before dependents, so a reader of the
# generated file sees the database before the services that wait for it.
COMPOSE_ORDER = ["postgres", "api", "worker", "web"]
# Where each block's compose fragments live.
FRAGMENT_DIR = {"web": "frontend/compose", "api": "backend/compose",
                "worker": "backend/compose", "postgres": "backend/compose"}
# The block Caddy points at: web if the project has one, else the api.
PUBLIC_ORDER = ["web", "api"]
# Data routes the template ships. `set`/`add` only rewrite deploy/app-deploy's
# DATA_ROUTE while it still holds one of these, never a route you chose.
DEFAULT_DATA_ROUTES = {"", "/api/items", "/api/hello"}

OPEN = re.compile(r"^\s*(?:#|<!--|//)\s*block:(\S+?)\s*(?:-->)?\s*$")
CLOSE = re.compile(r"^\s*(?:#|<!--|//)\s*/block\s*(?:-->)?\s*$")

ENVS = {
    "dev": ("docker-compose.yml", """\
# LOCAL DEVELOPMENT ONLY. Production is compose.deploy.yml.
#
# Unlike production, this publishes ports (there is no shared Caddy on a
# laptop) and mounts source for hot reload. Ports are overridable in .env
# (DEV_WEB_PORT / DEV_API_PORT / DEV_DB_PORT).
#
#   docker compose up --build
"""),
    "deploy": ("compose.deploy.yml", """\
# PRODUCTION and STAGING — Raspberry Pi 5, behind the shared Caddy + cloudflared.
#
#   docker --context pi-deploy compose -f compose.deploy.yml -p <app> up -d --build
#   (swap pi-deploy -> pi-remote when off the home LAN)
#
# Staging is this same file with STACK=<app>-staging, which namespaces every
# container, image and data directory; deploy/app-deploy sets it.
#
# THE HOUSE PATTERN — three rules, each load-bearing:
#  1. NO published ports and NO Caddy of our own. The Pi runs ONE shared Caddy
#     plus a cloudflared connector; no inbound ports are open on the router.
#  2. The public block joins the EXTERNAL `web` network so that shared Caddy can
#     reach it by container name. Blocks are written http://, deliberately:
#     Cloudflare terminates TLS at its edge and Caddy has no public port on
#     which to complete an ACME challenge.
#  3. Persistent data BIND-MOUNTS from /mnt/ssd/apps/<stack>/, never baked into
#     an image, so a code-only redeploy never touches data.
#
# `-p <app>` is NOT optional: a different project name builds a second image set
# and then collides on container_name.
"""),
    "e2e": ("compose.e2e.yml", """\
# Ephemeral stack for the end-to-end tests — run by scripts/e2e.sh.
#
# Deliberately NOT compose.deploy.yml: that bind-mounts /mnt/ssd/apps/..., which
# only exists on the Pi, and joins the external `web` network, which only exists
# where the shared Caddy runs. Everything here is repo-relative and disposable,
# so a CI runner or a laptop can bring the whole app up from a clean checkout.
#
#   docker compose -f compose.e2e.yml -p <app>-e2e up -d --build
"""),
}


class BlockError(Exception):
    pass


# --------------------------------------------------------------- manifest --

def load(root: Path) -> dict:
    path = root / MANIFEST
    if not path.exists():
        raise BlockError(f"{MANIFEST} not found in {root}")
    return json.loads(path.read_text())


def save(root: Path, manifest: dict) -> None:
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (root / MANIFEST).write_text(_compact(text))


def _compact(text: str) -> str:
    """Keep short string lists on one line, as the hand-written manifest has them."""
    def join(m: re.Match) -> str:
        items = re.findall(r'"(?:[^"\\]|\\.)*"', m.group(2))
        one = m.group(1) + "[" + ", ".join(items) + "]"
        return one if len(one) <= 100 else m.group(0)
    return re.sub(r'(^\s*"[^"]+": )\[\n((?:\s*"(?:[^"\\]|\\.)*",?\n)+)\s*\]', join, text, flags=re.M)


def names(manifest: dict) -> set[str]:
    return set(manifest["blocks"]) | set(manifest["targets"])


def active(selected: list[str], target: str) -> set[str]:
    return set(selected) | {target}


def satisfied(when: str, on: set[str]) -> bool:
    if "|" in when:
        return any(p in on for p in when.split("|"))
    return all(p in on for p in when.split("+"))


def when_names(when: str) -> list[str]:
    return re.split(r"[+|]", when)


def validate(manifest: dict, selected: list[str], target: str) -> None:
    blocks, targets = manifest["blocks"], manifest["targets"]
    if not selected:
        raise BlockError("choose at least one block")
    unknown = [b for b in selected if b not in blocks]
    if unknown:
        raise BlockError(f"unknown block(s): {', '.join(unknown)} — known: {', '.join(blocks)}")
    if target not in targets:
        raise BlockError(f"unknown target {target!r} — known: {', '.join(targets)}")
    for b in selected:
        spec = blocks[b]
        missing = [r for r in spec.get("requires", []) if r not in selected]
        if missing:
            raise BlockError(f"{b} requires {', '.join(missing)}")
        any_of = spec.get("requires_any", [])
        if any_of and not any(r in selected for r in any_of):
            raise BlockError(f"{b} needs one of: {', '.join(any_of)} (something has to run its migrations)")
    refused = [b for b in selected if b not in targets[target]["allows"]]
    if refused:
        raise BlockError(f"target {target} cannot host: {', '.join(refused)} "
                         f"(it allows {', '.join(targets[target]['allows'])})")


def ordered(manifest: dict, selected) -> list[str]:
    return [b for b in manifest["blocks"] if b in selected]


# ------------------------------------------------------------ file owners --

def matches(pattern: str, rel: str) -> bool:
    return rel == pattern or rel.startswith(pattern.rstrip("/") + "/") or fnmatch.fnmatchcase(rel, pattern)


def kept(manifest: dict, rel: str, on: set[str]) -> bool:
    return all(satisfied(rule["when"], on)
               for rule in manifest["files"]
               if any(matches(p, rel) for p in rule["paths"]))


def owned(manifest: dict, rel: str) -> bool:
    return any(matches(p, rel) for rule in manifest["files"] for p in rule["paths"])


def expand(root: Path, pattern: str) -> list[Path]:
    if any(c in pattern for c in "*?["):
        return sorted(root.glob(pattern))
    path = root / pattern
    return [path] if path.exists() or path.is_symlink() else []


def removals(root: Path, manifest: dict, on: set[str]) -> list[Path]:
    """Every existing path a rule no longer satisfied by `on` owns."""
    out: list[Path] = []
    for rule in manifest["files"]:
        if satisfied(rule["when"], on):
            continue
        for pattern in rule["paths"]:
            out.extend(expand(root, pattern))
    # Drop paths already covered by a removed parent directory.
    out = sorted(set(out))
    return [p for p in out if not any(q != p and q in p.parents for q in out)]


def remove(root: Path, path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    parent = path.parent
    while parent != root and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


# ------------------------------------------------------------ marked text --

def strip_marked(text: str, on: set[str], known: set[str], where: str = "") -> str:
    """Drop `block:<when>` sections `on` does not satisfy. Kept sections keep
    their markers, so a later `set` can still remove them."""
    out: list[str] = []
    current: str | None = None
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        opened, closed = OPEN.match(line), CLOSE.match(line)
        if opened:
            if current is not None:
                raise BlockError(f"{where}:{n}: nested block section")
            current = opened.group(1)
            bad = [x for x in when_names(current) if x not in known]
            if bad:
                raise BlockError(f"{where}:{n}: unknown name(s) in block:{current}: {', '.join(bad)}")
        elif closed and current is None:
            raise BlockError(f"{where}:{n}: /block without an opening block:")
        if current is None or satisfied(current, on):
            out.append(line)
        if closed:
            current = None
    if current is not None:
        raise BlockError(f"{where}: block:{current} is never closed")
    return "".join(out)


def sections(text: str) -> list[str]:
    return [m.group(1) for m in map(OPEN.match, text.splitlines()) if m]


# ---------------------------------------------------------------- compose --

def fragments(root: Path, manifest: dict, selected: list[str], env: str) -> list[list[str]]:
    """One include entry per block: its base fragment plus the glue it needs."""
    public = next((b for b in PUBLIC_ORDER if b in selected), None)
    entries = []
    for block in [b for b in COMPOSE_ORDER if b in selected]:
        d = FRAGMENT_DIR[block]
        base = f"{d}/{block}.{env}.yml"
        if not (root / base).exists():
            continue
        entry = [base]
        for other in ordered(manifest, selected):
            glue = f"{d}/{block}.{env}.with-{other}.yml"
            if other != block and (root / glue).exists():
                entry.append(glue)
        extra = f"{d}/{block}.{env}.public.yml"
        if block == public and (root / extra).exists():
            entry.append(extra)
        entries.append(entry)
    return entries


def render_compose(root: Path, manifest: dict, env: str) -> str | None:
    selected, target = manifest["selected"], manifest["target"]
    if env == "deploy" and target != "pi-compose":
        return None
    entries = fragments(root, manifest, selected, env)
    if not entries:
        return None
    _, header = ENVS[env]
    lines = [
        f"# GENERATED by scripts/blocks.py from {MANIFEST} (blocks: {', '.join(selected)}).",
        "# Do not edit by hand: change the fragments it includes, then run",
        "#   python3 scripts/blocks.py sync",
        "# Each block's fragments live next to its code; docs/BLOCKS.md explains them.",
        "#",
        *header.rstrip("\n").splitlines(),
        "",
    ]
    if env == "deploy":
        lines += ["# Lets `docker compose` run without -p; app-deploy passes -p anyway.",
                  "name: ${STACK:-${APP_NAME}}", ""]
    lines.append("include:")
    for entry in entries:
        # project_directory: every path in a fragment resolves from the repo
        # root, and .env is the root's — exactly as in one hand-written file.
        if len(entry) == 1:
            lines.append(f"  - path: {entry[0]}")
        else:
            lines.append("  - path:")
            lines += [f"      - {p}" for p in entry]
        lines.append("    project_directory: .")
    return "\n".join(lines) + "\n"


def data_route(selected) -> str:
    if "api" in selected and "postgres" in selected:
        return "/api/items"
    return "/api/hello" if "api" in selected else ""


def sync_deploy_agent(root: Path, selected: list[str], reset_route: bool) -> list[str]:
    path = root / "deploy" / "app-deploy"
    if not path.exists():
        return []
    text = path.read_text()
    new = re.sub(r'^BLOCKS="[^"]*"', f'BLOCKS="{" ".join(selected)}"', text, count=1, flags=re.M)
    route = re.search(r'^DATA_ROUTE="([^"]*)"', new, flags=re.M)
    if reset_route and route and route.group(1) in DEFAULT_DATA_ROUTES:
        new = new.replace(route.group(0), f'DATA_ROUTE="{data_route(selected)}"', 1)
    if new != text:
        path.write_text(new)
        return ["deploy/app-deploy"]
    return []


def sync(root: Path, manifest: dict, reset_route: bool = False, dry: bool = False) -> list[str]:
    changed = []
    for env, (name, _) in ENVS.items():
        path = root / name
        text = render_compose(root, manifest, env)
        if text is None:
            if path.exists():
                changed.append(f"{name} (removed)")
                if not dry:
                    path.unlink()
        elif not path.exists() or path.read_text() != text:
            changed.append(name)
            if not dry:
                path.write_text(text)
    if not dry:
        changed += sync_deploy_agent(root, manifest["selected"], reset_route)
    return changed


# --------------------------------------------------------------- commands --

def cmd_set(root: Path, blocks: list[str], target: str, dry: bool) -> int:
    manifest = load(root)
    validate(manifest, blocks, target)
    on = active(blocks, target)
    before = active(manifest["selected"], manifest["target"])
    added = sorted(on - before)
    if target in added and all(expand(root, p) for rule in manifest["files"]
                               if rule["when"] == target for p in rule["paths"]):
        added.remove(target)   # its files are here (the template has every target's)
    if added:
        # Files for a newly selected block are not here to keep; `add` copies
        # them in from the template. Refusing is better than a half block.
        raise BlockError(f"`set` only removes; {', '.join(added)} is not in this project yet. "
                         f"Use: python3 scripts/blocks.py add {' '.join(a for a in added if a in manifest['blocks']) or '<block>'}"
                         f" --from <template checkout>" + (f" --target {target}" if target in added else ""))
    gone = removals(root, manifest, on)
    for p in gone:
        print(f"  remove {p.relative_to(root)}")
        if not dry:
            remove(root, p)
    known = names(manifest)
    for rel in manifest["marked"]:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text()
        new = strip_marked(text, on, known, rel)
        if new != text:
            print(f"  prune  {rel}")
            if not dry:
                path.write_text(new)
    manifest["selected"], manifest["target"] = ordered(manifest, blocks), target
    for name in sync(root, manifest, reset_route=True, dry=dry):
        print(f"  write  {name}")
    if not dry:
        save(root, manifest)
    print(("would set" if dry else "set") + f": {', '.join(manifest['selected'])} on {target}")
    return 0


def is_template(root: Path) -> bool:
    try:
        return bool(json.loads((root / ".agent-context.json").read_text()).get("is_template"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def tracked(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True)
        return out.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        skip = {".git", "node_modules", ".venv", "__pycache__", "dist"}
        return [str(p.relative_to(root)) for p in root.rglob("*")
                if p.is_file() and not skip & set(p.relative_to(root).parts)]


def substitutions(root: Path) -> list[tuple[str, str]]:
    """The placeholder rewrites init-project.sh made, so copied files match."""
    ctx = json.loads((root / ".agent-context.json").read_text())
    app = ctx.get("project")
    if ctx.get("is_template", False) or not app:
        raise BlockError("`add` runs in an initialised project, not in the template itself")
    # Spelled in pieces: init-project.sh rewrites these words in every file it
    # does not skip, and this list has to survive that.
    ph = "CHANGE" + "ME"
    return [("<App" + " name>", app), (f"{ph}-app-label", f"{app}-runner"),
            (f"{ph}-app", app), (ph, app), ("project" + "-template", app)]


def cmd_add(root: Path, new_blocks: list[str], source: Path, target: str | None, dry: bool) -> int:
    manifest = load(root)
    source = source.resolve()
    template = load(source)
    blocks = ordered(template, set(manifest["selected"]) | set(new_blocks))
    target = target or manifest["target"]
    validate(template, blocks, target)
    before = active(manifest["selected"], manifest["target"])
    on = active(blocks, target)
    subs = substitutions(root)

    copied = 0
    for rel in tracked(source):
        if not owned(template, rel) or not kept(template, rel, on) or kept(template, rel, before):
            continue
        dest = root / rel
        if dest.exists():
            continue
        print(f"  copy   {rel}")
        copied += 1
        if dry:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = source / rel
        try:
            text = src.read_text()
            for old, new in subs:
                text = text.replace(old, new)
            dest.write_text(text)
            shutil.copymode(src, dest)
        except UnicodeDecodeError:
            shutil.copy2(src, dest)

    # Marked files: if the project's copy is still what the template gives for
    # the OLD selection, it was never edited and can simply be regenerated.
    # Otherwise say which sections to merge by hand, rather than guess.
    known = names(template)
    manual = []
    for rel in template["marked"]:
        src, dest = source / rel, root / rel
        if not src.exists():
            continue
        text = src.read_text()
        for old, new in subs:
            text = text.replace(old, new)
        want = strip_marked(text, on, known, rel)
        if not dest.exists():
            continue
        if dest.read_text() == want:
            continue
        if dest.read_text() == strip_marked(text, before, known, rel):
            print(f"  update {rel}")
            if not dry:
                dest.write_text(want)
        else:
            new_sections = sorted({s for s in sections(text) if satisfied(s, on) and not satisfied(s, before)})
            if new_sections:
                manual.append(f"{rel}: block:{', block:'.join(new_sections)}")

    # The template's catalogue replaces ours: it knows the rules for the files
    # just copied, and this project's copy may predate them.
    manifest = {**template, "selected": blocks, "target": target}
    for name in sync(root, manifest, reset_route=True, dry=dry):
        print(f"  write  {name}")
    if not dry:
        save(root, manifest)
    print(("would add" if dry else "added") + f": now {', '.join(blocks)} on {target} ({copied} files copied)")
    if manual:
        print("\nThese files were edited in this project, so merge their new sections by hand")
        print(f"from the template ({source}):")
        for m in manual:
            print(f"  {m}")
    return 0


def cmd_check(root: Path) -> int:
    manifest = load(root)
    errors: list[str] = []
    selected, target = manifest["selected"], manifest["target"]
    try:
        validate(manifest, selected, target)
    except BlockError as exc:
        errors.append(str(exc))
    known = names(manifest)
    for rule in manifest["files"]:
        bad = [x for x in when_names(rule["when"]) if x not in known]
        if bad:
            errors.append(f"{MANIFEST}: unknown name(s) in when {rule['when']!r}: {', '.join(bad)}")
    on = active(selected, target)
    if is_template(root):
        # The template carries every block and every target so that a project
        # can be cut from it; only an initialised project must be pruned.
        on = names(manifest)
    for p in removals(root, manifest, on):
        errors.append(f"{p.relative_to(root)} belongs to a block this project does not have "
                      f"— run: python3 scripts/blocks.py set --blocks {','.join(selected)} --target {target}")
    for rel in manifest["marked"]:
        path = root / rel
        if not path.exists():
            continue
        try:
            text = path.read_text()
            if strip_marked(text, on, known, rel) != text:
                errors.append(f"{rel} holds sections for blocks this project does not have")
        except BlockError as exc:
            errors.append(str(exc))
    for env, (name, _) in ENVS.items():
        want = render_compose(root, manifest, env)
        path = root / name
        have = path.read_text() if path.exists() else None
        if want != have:
            errors.append(f"{name} is out of date with {MANIFEST} — run: python3 scripts/blocks.py sync")
    agent = root / "deploy" / "app-deploy"
    if agent.exists():
        m = re.search(r'^BLOCKS="([^"]*)"', agent.read_text(), flags=re.M)
        if not m or m.group(1).split() != selected:
            errors.append("deploy/app-deploy BLOCKS does not match — run: python3 scripts/blocks.py sync")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if not errors:
        print(f"blocks ok: {', '.join(selected)} on {target}")
    return 1 if errors else 0


def cmd_env(root: Path, github: bool) -> int:
    manifest = load(root)
    selected, target = manifest["selected"], manifest["target"]
    flags = {b: b in selected for b in manifest["blocks"]}
    flags["python"] = any(flags[b] for b in ("api", "worker", "postgres"))
    public = next((b for b in PUBLIC_ORDER if b in selected), "")
    if github:
        for k, v in flags.items():
            print(f"{k}={'true' if v else 'false'}")
        print(f"target={target}")
        print(f"blocks={' '.join(selected)}")
        print(f"template={'true' if is_template(root) else 'false'}")
        return 0
    print(f'BLOCKS="{" ".join(selected)}"')
    print(f'TARGET="{target}"')
    for k, v in flags.items():
        print(f"HAS_{k.upper()}={1 if v else 0}")
    print(f'PUBLIC_BLOCK="{public}"')
    print(f'DATA_ROUTE="{data_route(selected)}"')
    return 0


def cmd_checks(root: Path) -> int:
    manifest = load(root)
    seen: list[str] = []
    for b in manifest["selected"]:
        for c in manifest["blocks"][b].get("checks", []):
            if c not in seen:
                seen.append(c)
    print("\n".join(seen))
    return 0


def cmd_describe(root: Path) -> int:
    manifest = load(root)
    parts = [manifest["blocks"][b]["summary"] for b in manifest["selected"]]
    print("; ".join(parts) + f". Deployed as: {manifest['targets'][manifest['target']]['summary']}.")
    return 0


def cmd_status(root: Path) -> int:
    manifest = load(root)
    for b, spec in manifest["blocks"].items():
        mark = "x" if b in manifest["selected"] else " "
        print(f"[{mark}] {b:<9} {spec['summary']}")
    t = manifest["target"]
    print(f"target: {t} — {manifest['targets'][t]['summary']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("set", help="keep only these blocks (removes the rest)")
    p.add_argument("--blocks", required=True, help="comma-separated, e.g. web,api,postgres")
    p.add_argument("--target", help="pi-compose or pages (default: unchanged)")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("add", help="copy blocks in from a template checkout")
    p.add_argument("blocks", nargs="+")
    p.add_argument("--from", dest="source", type=Path, required=True)
    p.add_argument("--target")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("sync", help="regenerate the root compose files from the manifest")
    sub.add_parser("check", help="fail if manifest, files and compose disagree")
    p = sub.add_parser("env", help="shell variables (or GitHub outputs) describing the blocks")
    p.add_argument("--github", action="store_true")
    sub.add_parser("checks", help="print the check commands for these blocks")
    sub.add_parser("describe", help="print the stack in one line")
    sub.add_parser("status", help="list blocks and the target")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.cmd == "set":
            blocks = [b.strip() for b in args.blocks.split(",") if b.strip()]
            return cmd_set(root, blocks, args.target or load(root)["target"], args.dry_run)
        if args.cmd == "add":
            blocks = [b for arg in args.blocks for b in arg.split(",") if b]
            return cmd_add(root, blocks, args.source, args.target, args.dry_run)
        if args.cmd == "sync":
            for name in sync(root, load(root)):
                print(f"  write  {name}")
            return 0
        return {"check": cmd_check, "checks": cmd_checks, "describe": cmd_describe,
                "status": cmd_status}.get(args.cmd, lambda r: cmd_env(r, args.github))(root)
    except BlockError as exc:
        print(f"blocks: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
