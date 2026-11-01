# The alert for a read-only volume cleared itself while the volume stayed read-only

**Date:** 2026-10-12 23:44 UTC to 2026-10-13 16:00 UTC
**Component:** `VolumeRemountedReadOnly` alert; the `soiree-pg` CNPG cluster
**Severity:** 2 of 3 replicas down for 14 hours; the primary stayed up, so the application kept its database

This is a recurrence of [`2026-10-12-truenas-update-readonly-pv-remount.md`](2026-10-12-truenas-update-readonly-pv-remount.md). The cause of the read-only volume is the same. This file records 2 facts that the first file does not: a volume turns read-only hours after the storage returns, and the alert written to catch it cleared itself while the fault remained.

## Effect

The volumes of `soiree-pg-2` and `soiree-pg-3` turned read-only. Each instance crash-looped about 190 times. `soiree-pg` reported 1 of 3 instances ready.

`soiree-pg` came through the event of 2026-10-12 with 3 of 3 instances ready. A volume therefore turns read-only hours after the storage returns. Read each cluster again on the day after an event of this kind.

The primary `soiree-pg-1` was not affected. The application kept its database and there was no outage.

## Cause

The read-only mount has the same cause as the first event. Read that file.

The second cause is the alert. `VolumeRemountedReadOnly` read the change, not the state:

```promql
node_filesystem_readonly{...} == 1 and changes(node_filesystem_readonly[2h]) > 0
```

`changes()` stops matching 2 hours after the transition. The rule therefore cleared itself while the volume was still read-only.

| Time (UTC) | State |
|---|---|
| 10-12 23:44 | The mount turns read-only. |
| 10-12 23:45 | The alert goes to pending. |
| 10-12 23:50 | The alert fires, 6 minutes after the fault. |
| 10-13 01:44 | The alert clears. The volume is still read-only. |
| 10-13 14:04 | `KubePodCrashLooping` raises the fault, 14 hours after 23:44. |

The clear at 01:44 is 23:44 plus the 2 hour window. That is the proof that the window caused it.

CAUTION: Read the series at a step of 1 minute. A step of 5 minutes puts the fire at 23:49 and the clear at 01:39. Those 2 times fit no window, and they invite the reader to doubt a correct conclusion.

An alert that clears while the fault remains is worse than no alert. The record says that the cluster recovered.

## Correction

1. Delete each affected replica, so that kubelet mounts the volume again:

```bash
kubectl --context yornik-sharkshere -n soiree delete pod soiree-pg-2
kubectl --context yornik-sharkshere -n soiree delete pod soiree-pg-3
```

Each instance was ready again in under 60 seconds with 0 restarts.

NOTE: The primary stayed up through the fault and through the correction, so no failover happened.

2. Add `keep_firing_for: 24h` to the rule in `apps/values.yaml`. The alert then holds for 24 hours after the expression stops matching.

## Prevention

The hold has 2 costs. Both are in the rule comment and in the alert description, where an operator reads them.

| Cost | Detail |
|---|---|
| The alert outlives the repair | `keep_firing_for` does not read the repair. The expression stops matching for a repair and for an expired window alike. Alertmanager repeats a firing alert every 12 hours, so a repaired volume sends about 2 more mails. |
| A second fault is silent | A volume that turns read-only again inside the hold raises no second alert. Its mail reads the same as the mail for the first fault. |

CAUTION: The alert clears about 26 hours after the transition. That is the 2 hour window and then the 24 hour hold. The volume can still be read-only.

Read `node_filesystem_readonly` for the mount to tell a repair from a fault that continues.

Both costs come from the `changes()` guard. The guard exists because the orphaned `globalmount` paths read 1 for ever. Remove them from the nodes, then alert on `node_filesystem_readonly == 1` alone. That state starts when the volume breaks and ends when an operator repairs it, and at no other time. See the open item in the first file.

## Later change (2026-11-01)

The 24 hour hold kept a repaired volume firing for a day after the TrueNAS 27 update, and Alertmanager sent the same mail again 12 hours in. The orphaned `globalmount` paths that the guard worked around were gone: no CSI mount read 1 except the 3 CIFS shares, and none read 1 for more than half of the last 7 days. The rule now reads `node_filesystem_readonly == 1` alone, with `for: 5m` and no `keep_firing_for`. It fires while a volume is read-only and ends at the repair.

CAUTION: An orphaned `globalmount` that reads 1 fires the alert until it is removed from the node. Remove the mount; do not add the guard back.

## Evidence

- `soiree-pg-2` instance manager: `open /var/lib/postgresql/data/pgdata/pg_wal/_cnpg_probe_7TH2: read-only file system`.
- `soiree-pg-2` 191 restarts, `soiree-pg-3` 190 restarts, both 1 of 2 containers ready.
- The `ALERTS` series at a step of 1 minute: pending 23:45 to 23:49, firing 23:50 to 01:43.
- `node_filesystem_readonly` for the mount on `talos-ako-s53`: 0 until 23:43, 1 from 23:44.
- Alertmanager `repeat_interval` is 12h, read from the running Alertmanager on 2026-10-13. The value is in the SOPS-encrypted `manifests/monitoring/alertmanager-config.enc.yaml`, so a reader without the key confirms it against the running Alertmanager, not against the repository.
- After the correction, all 4 CNPG clusters report `Cluster in healthy state` and every pod in the cluster is ready.
