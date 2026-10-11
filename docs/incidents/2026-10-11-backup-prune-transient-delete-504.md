# One object storage timeout made a week of alerts for a problem that corrected itself

**Date:** 2026-10-11
**Component:** `prune-omni-snapshots` CronJob, namespace `backup-prune`, bucket `omni-yornik` in fsn1
**Severity:** no data lost, no backup lost; 1 alert that stays on for 7 days

## Effect

The Job `prune-omni-snapshots-29861625` failed at 05:46 UTC. Alertmanager sent `KubeJobFailed` and kept it firing.

The alert was still firing 13 hours later. It describes a condition that had already corrected itself.

No snapshot was lost. The etcd snapshots in `omni-yornik` were complete and current through the whole event.

## Cause

Hetzner Object Storage answered `504 Gateway Timeout` to 1 of the 8 `DELETE` requests in the run.

`prune.py` counted the failure and exited 1. The Job has `backoffLimit: 0`, so there was no second attempt. The pod log was:

```
keep      48 backups, 4.63 GB
delete     8 backups, 0.81 GB
  could not delete cea8d004-.../FFFFFFFF9539B0B9.snapshot: HTTP Error 504: Gateway Timeout
deleted 7, failed 1
```

Three facts make this a false alarm rather than a fault:

1. A `DELETE` on an object store is idempotent. A timeout is safe to repeat.
2. The object stays outside the keep set as it ages, so the next daily run deletes it. The condition corrects itself in 24 hours.
3. The Job has `ttlSecondsAfterFinished: 604800`. A failed Job stays for 7 days, and `KubeJobFailed` reads the Job, so the alert outlives the condition by that much.

The guard for a real fault did not fire. The bucket held 56 snapshots and the newest was inside the `STALE_DAYS` window, so the run computed the policy and deleted correctly.

NOTE: The `prune-gitlab-backups` Job ran 30 minutes earlier the same morning and completed. Both Jobs read the same Secret `backup-prune-s3`. That rules out the credentials.

## Correction

1. An operator deleted the failed Job. The alert cleared.

```bash
kubectl --context yornik-sharkshere -n backup-prune delete job prune-omni-snapshots-29861625
```

2. `delete_object()` in `manifests/backup-prune/prune.py` now repeats a transient failure. It makes 4 attempts with a delay of 1, 2 and 4 seconds.

## Prevention

`prune.py` separates a transient answer from a real one.

| Answer | Action |
|---|---|
| 429, 500, 502, 503, 504, or a timeout | Repeat the request, up to 4 attempts. |
| Any other 4xx | Raise at once. A wrong key or a missing permission does not improve. |

The exit code still reports a delete that fails every attempt. The alert keeps its meaning for a fault that lasts.

CAUTION: Do not make the Job exit 0 when a delete fails. The exit code is the only signal that a delete did not happen.

Tests in `manifests/backup-prune/test_prune.py` cover the 4 cases: a 504 that succeeds on the second attempt, the delay between attempts, a 403 that is not repeated, and a failure on every attempt.

## Evidence

- Pod log of `prune-omni-snapshots-29861625-bwrss`, above. Container state: `exitCode=1`, `reason=Error`, `finished=2026-10-11T05:46:03Z`.
- The 3 runs before it completed: `29857305`, `29858745`, `29860185`.
- `prune-gitlab-backups-29861595` completed at 05:15 UTC the same morning.
- After the delete, `kube_job_failed{namespace="backup-prune"} > 0` returned 0 results, `ALERTS{alertname="KubeJobFailed"}` returned 0 results, and Alertmanager held 1 alert, `Watchdog`.
