# GitLab backup job cannot dump the database (client version)

**Date:** 2026-07-10
**Component:** `gitlab` Application, toolbox backup CronJob
**Severity:** backup gap, no user-facing effect

## Effect

The GitLab toolbox backup CronJob failed. No tarball reached the `yornik-gitlab-backups` bucket.

## Cause

The toolbox image ships a `pg_dump` client at version 17.x. The GitLab database runs on a CloudNativePG cluster at Postgres 18. A `pg_dump` client cannot dump a server with a newer major version. The failure was verified by hand on 2026-07-10.

## Correction

Pass `--skip db` to the backup job through `toolbox.backups.cron.extraArgs`. The job then backs up only the repository data from gitaly.

The database has its own protection. CloudNativePG takes a base backup every three hours. The barman-cloud plugin archives WAL continuously to the `cnpg-wal` bucket.

## Prevention

A restore now has two parts. Restore the tarball from the toolbox backup for repository data. Restore the database with a CloudNativePG point-in-time recovery.

NOTE: The gitaly data lives on an iSCSI zvol. The NAS file-level backup and the ZFS snapshot task on `Big_Pool/Share` do not see it. The toolbox CronJob is the only backup path for hosted repositories. Do not disable it.

## Evidence

- `apps/values.yaml`, comment above `toolbox.backups.cron.extraArgs`.
