# GitLab backup failed while it copied object storage buckets

**Date:** 2026-10-21
**Component:** `gitlab` Application, toolbox backup CronJob, Hetzner Object Storage
**Severity:** no data lost, no backup lost; 1 alert that stays on until an operator deletes the Job

## Effect

The Job `gitlab-toolbox-backup-29875890` failed at 03:55 UTC. Alertmanager sent `KubeJobFailed` and kept it firing.

The repository dump finished in every attempt. The previous tarball was 33 hours old. The CNPG base backups and WAL archive were not affected.

## Cause

`backup-utility --skip db` still copies the object storage buckets. It downloads each bucket with `s3cmd` and packs the files into a tarball.

Hetzner Object Storage answered `503 SlowDown` and `504 Gateway Timeout` during the download. `s3cmd` retried and then failed. The log was:

```
Dumping artifacts ...
creation of working directory of artifacts failed
WARNING: Remote file ''. S3Error: 504 (GatewayTimeout): The server did not respond in time.
```

The container exited with `Error` and restarted. The Job has `restartPolicy: OnFailure` and `backoffLimit: 6`. The restarts at 03:34, 03:36, 03:40, 03:44 and 03:55 used the limit. The last attempt failed on `packages`.

Three facts explain why this repeats:

1. The download takes 5 to 15 minutes and sends one request for each object. Each request can fail.
2. A restart begins again at the repositories. It does not continue where the last attempt stopped.
3. Run `29871570` also restarted once (`reason=Error`) before it completed. The fault was intermittent before 2026-10-21.

The `registry` bucket answered `403 AccessDenied` in every run. The utility skips it. This did not cause the failure.

NOTE: The tarball is stored in the `yornik-gitlab-backups` bucket, in the same provider as the buckets it copies. The copy did not protect against the loss of Hetzner Object Storage.

## Correction

1. An operator deleted the failed Job. The alert cleared.

```bash
kubectl --context yornik-sharkshere -n gitlab delete job gitlab-toolbox-backup-29875890
```

2. `toolbox.backups.cron.extraArgs` in `apps/values.yaml` now skips every object storage component: `registry`, `uploads`, `artifacts`, `lfs`, `packages`, `external_diffs`, `terraform_state`, `pages`, `ci_secure_files`, `agent_plan_content` and `ci_catalog_bundles`.

## Prevention

The Job now needs only the gitaly service and one upload of the tarball. The repository data is the purpose of this Job. See [2026-07-10-gitlab-backup-pg-dump-version.md](2026-07-10-gitlab-backup-pg-dump-version.md).

WARNING: Nothing outside Hetzner holds a copy of the object storage buckets. The buckets hold CI artifacts, uploads, LFS objects, packages and registry images. If a bucket is lost, the data is lost. To change this, add a bucket replication or a `rclone` job to a second provider. Do not return to `backup-utility` for this.

NOTE: A restore uses the tarball for repository data and a CNPG point-in-time recovery for the database. The tarball lists the skipped components in `backup_information.yml`, so the restore does not look for them.

## Evidence

- Loki, pod `gitlab-toolbox-backup-29875890-4tv8g`, 03:30 to 03:55 UTC. The pod restarted its container 6 times. Each restart logged `Attempting to run ... backup-utility --skip db`.
- `kube_pod_container_status_last_terminated_reason` was `Error` for this pod and for `gitlab-toolbox-backup-29871570-lbdhj`.
- Job condition: `BackoffLimitExceeded`, `startTime=2026-10-21T03:30:00Z`.
