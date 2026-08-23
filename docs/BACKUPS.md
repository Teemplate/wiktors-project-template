# Backups

**Optional, and worth adding the moment the app holds data a human would miss.**
Most projects never back up at all, and of those that do, few have ever *proved*
a restore works. An unverified backup is a belief, not a backup.

The deploy agent already takes a **pre-deploy `pg_dump`** and refuses to run
migrations without one (keeping the newest 20 in
`/mnt/ssd/apps/<app>/backups/`). That covers the most common loss — a bad
migration — and needs no setup. Everything below covers the rest: disk failure,
ransomware, and "someone deleted the wrong rows three weeks ago".

## The shape that works

Three systemd user timers on the Pi:

1. **Nightly dump, encrypted to a public key.** Use [`age`](https://age-encryption.org):
   ```bash
   pg_dump -U "$PGUSER" -d "$PGDB" -Fc \
     | age -r "$AGE_PUBLIC_KEY" > "backup-$(date +%F).age"
   ```
   **The Pi holds only the public key.** It can therefore *write* backups and
   cannot *read* them. If the Pi is compromised, the attacker gets ciphertext.
   The private key lives on the laptop, backed up separately — losing it means
   losing every backup, so store it where you store passwords, not on the Pi.

2. **Pull them off the Pi.** A backup on the same disk as the database is not a
   backup. Pull to the laptop (or object storage) on a schedule; the encryption
   means the destination does not need to be trusted.

3. **Verify a restore, automatically.** The only check that means anything:
   decrypt the newest backup, `pg_restore` it into a throwaway container, and
   assert the row counts are sane. Run it weekly. A backup nobody has restored
   is a backup that does not work yet — this is how you find the truncated
   dumps, the missing extension, the changed `pg_dump` version.

## Retention that survives a slow mistake

Keep nightlies for a fortnight and one weekly for a quarter. Nightly-only
retention cannot recover from damage nobody noticed for three weeks, which is
the realistic failure — not the dramatic one.

## Restoring

Write the restore command down **before** you need it, and make sure it is in
this file rather than in someone's shell history:

```bash
age -d -i ~/.age/key.txt backup-YYYY-MM-DD.age > restore.dump
docker exec -i <app>-db pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists < restore.dump
```

Practise it once on staging. The first time you run a restore should not be the
day you need it.
