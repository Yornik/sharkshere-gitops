# Restoring soiree-pg

A backup that has never been restored is not a backup. This is the procedure,
and it is meant to be **rehearsed** — run it against a scratch namespace while
nothing is wrong, so that the first time it matters is not the first time it is
attempted.

Applies to the `soiree-pg` CloudNativePG cluster in namespace `soiree`:
3 instances, data and WAL on `truenas-ssd-iscsi`, WAL archive and base backups
to Hetzner Object Storage via barman-cloud (`s3://cnpg-wal/`, `serverName:
soiree-pg`).

## Before you need it: does the archive actually work?

Most restore failures are archive failures that nobody noticed. Check first —
this is also the whole of the quarterly drill's "is it working" half.

```bash
kubectl --context yornik-sharkshere -n soiree get cluster soiree-pg \
  -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")]}{"\n"}'

# Base backups that have actually completed:
kubectl --context yornik-sharkshere -n soiree get backup
```

The failure mode worth knowing: Postgres will not recycle a WAL segment the
archiver has not confirmed. If uploads are failing, `.ready` files accumulate
until the WAL volume fills **on all three instances** and the cluster stops
accepting writes. It looks healthy right up until it stops. A red
`ContinuousArchiving` condition is therefore urgent even though nothing is
visibly broken.

```bash
# Pending WAL on the primary — should be a handful, not thousands.
kubectl --context yornik-sharkshere -n soiree exec -it soiree-pg-1 -- \
  sh -c 'ls /var/lib/postgresql/data/pgdata/pg_wal/archive_status/*.ready 2>/dev/null | wc -l'
```

## The drill (run this quarterly, and after any change to the backup config)

Restore into a **throwaway namespace**. Never practise against `soiree`.

1. **Note what you expect to find.** Query a figure from the live database
   first, so the restored copy can be checked against something concrete
   rather than eyeballed.

   ```bash
   kubectl --context yornik-sharkshere -n soiree exec -it soiree-pg-1 -- \
     psql -U postgres -d soiree -c \
     'select count(*) as items, coalesce(sum(unit*qty),0) as committed from budget_items;'
   ```

2. **Create the scratch namespace and copy the credentials into it.** The
   restore reads the same bucket, so it needs the same Secret. It is
   `cnpg-s3-wal`, and it must exist in the target namespace.

3. **Apply a recovery Cluster** — a new `Cluster` with `bootstrap.recovery`
   pointing at the same object store and `serverName: soiree-pg`, in the
   scratch namespace with a different cluster name. Use
   `recoveryTarget.targetTime` for a point in time, or omit it to recover to
   the end of the archive.

   Set `instances: 1` for a drill. Three is for production availability and
   only makes the rehearsal slower.

4. **Watch it recover.**

   ```bash
   kubectl --context yornik-sharkshere -n <scratch> get cluster -w
   kubectl --context yornik-sharkshere -n <scratch> logs -l cnpg.io/cluster=<name> -c postgres --tail=50
   ```

5. **Check the number from step 1 against the restored copy.** This is the
   step that makes it a drill rather than a ritual: a cluster that reaches
   `Cluster in healthy state` has proved it can start, not that your data is
   in it.

6. **Write down how long it took**, and delete the scratch namespace. The
   elapsed time is the number you actually need during an incident, and it is
   the one nobody has when they need it.

## Real recovery

Same procedure, with three differences.

- **Stop the writers first.** Scale the `soiree` Deployment to zero, or the app
  keeps writing to the database you are about to replace.
- **Disable auto-sync on the ArgoCD Application before touching anything.**
  Every app here runs `prune: true` and `selfHeal: true`; ArgoCD will revert a
  manual change within seconds and it will look like the restore silently
  failed.
- **Recover to a new cluster name, then move traffic.** Do not restore over the
  running cluster. If the recovery is wrong you want the original still there.

Point-in-time recovery is the reason the WAL archive exists: `targetTime` can
land just before a bad migration or a mistaken bulk edit, which a nightly base
backup alone cannot do.

## What this does not cover

- **The NAS cannot see inside an iSCSI zvol.** File-level NAS backup does not
  protect this database; the barman archive is the only copy. That is why a
  failing archive is an outage in waiting rather than a warning.
- **Application-level recovery.** A person deleting one budget line is not a
  database incident — the app's own change history answers that, and PITR for
  a single row is a sledgehammer.
- **Object storage failure.** Everything here assumes the Hetzner bucket is
  readable. There is no second copy of the archive today; if that matters,
  that is a separate decision to take deliberately rather than discover.
