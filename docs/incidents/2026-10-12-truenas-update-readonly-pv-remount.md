# A storage update turned 6 volumes read-only, and the pod that looked healthiest was the most broken

**Date:** 2026-10-12, recurrence 2026-10-12 23:44 UTC to 2026-10-13
**Component:** `truenas-ssd-iscsi` volumes; the `gitlab-pg` and `openproject-pg` CNPG clusters
**Severity:** OpenProject down about 5 hours; GitLab accepted connections but served no query for the same time. The recurrence on 2026-10-13 took 2 `soiree-pg` replicas and caused no outage.

## Effect

An operator updated TrueNAS at about 15:16 UTC. Alerts started in the same minute.

| Cluster | State |
|---|---|
| `openproject-pg` | 0 of 3 instances ready. Each pod restarted about 70 times. |
| `gitlab-pg` | 1 of 3 instances ready. The 1 ready instance served no query. |
| `shared-pg`, `soiree-pg` | 3 of 3 ready. No effect. |

OpenProject was down. GitLab answered on its port and failed every query. The web service and the runner crash-looped against it.

Alertmanager sent 9 alerts. They all came from 1 fault.

WARNING: `gitlab-pg-2` reported `Ready` with 0 restarts for 5 hours while it was broken. The readiness probe proves that the process accepts a connection. It does not prove that the process can read a file.

## Cause

The update took the iSCSI targets away while Postgres was writing. The volumes returned an I/O error. ext4 mounts with `errors=remount-ro`, so the kernel made each filesystem read-only.

A read-only ext4 does not become read-write again by itself. Postgres cannot write, so it exits. The pod restarts, finds the same read-only mount, and exits again.

The fault is per volume, not per node and not per storage class:

| Node | Read-only volume | Read-write volume on the same node |
|---|---|---|
| `talos-3xg-mwx` | `openproject-pg-1` | `gitlab-pg-2`, `shared-pg-1` |
| `talos-0wq-zph` | `gitlab-pg-3`, `openproject-pg-2` | `shared-pg-2`, `soiree-pg-3` |
| `talos-5oy-ktd` | `openproject-pg-3` | `soiree-pg-1` |
| `talos-ako-s53` | `gitlab-pg-1` | `shared-pg-3`, `soiree-pg-2` |

Every node served a read-write iSCSI volume at the same time. Only the filesystems that had a write in flight took the error. `shared-pg` and `soiree-pg` write little and came through untouched.

`gitlab-pg-2` crashed at no point, so it did not restart onto a fresh mount. Its Postgres kept the files it had already opened and failed on each new one:

```
FATAL: could not open file "base/5/2601": Read-only file system (SQLSTATE 42501)
```

That one pod then blocked the repair of the other 2. CNPG reads the state of the cluster from a ready instance. The request to `gitlab-pg-2` returned 500, so CNPG requeued:

```
Cannot extract Pod status  podName=gitlab-pg-2
Failed to extract instance status from ready instances. Attempting to requeue...
```

CNPG held the 4 PVCs of `gitlab-pg-1` and `gitlab-pg-3` as `danglingPVC` and built no pod for them. OpenProject recovered without this step because no OpenProject instance was ready, so CNPG took the rebuild path at once.

## Correction

An operator deleted each affected pod. The kubelet unmounts the volume and mounts it again, and the new mount is read-write.

1. Delete the OpenProject instances, one at a time:

```bash
kubectl --context yornik-sharkshere -n openproject delete pod openproject-pg-3
kubectl --context yornik-sharkshere -n openproject delete pod openproject-pg-1
kubectl --context yornik-sharkshere -n openproject delete pod openproject-pg-2
```

Each pod was ready again in about 30 seconds with 0 restarts. The primary moved to `openproject-pg-3`.

2. Delete the GitLab instances. Delete `gitlab-pg-2` as well, although it reports `Ready`:

```bash
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-1
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-3
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-2
```

CAUTION: Delete the instance that reports `Ready` last, and only after you read its log. While it is present, CNPG builds no pod for a dangling PVC. After the delete, CNPG rebuilt all 3 instances and the cluster was healthy in 40 seconds.

3. Delete the pods that crash-looped against the database, to clear the back-off:

```bash
kubectl --context yornik-sharkshere -n gitlab delete pod -l app=webservice
kubectl --context yornik-sharkshere -n gitlab delete pod -l app=gitlab-runner
```

## Prevention

A new alert, `VolumeRemountedReadOnly`, reports a CSI volume that turns read-only. It is in `additionalPrometheusRulesMap` in `apps/values.yaml`.

The alert reads the change, not the state. 6 mounts report `node_filesystem_readonly = 1` at all times, and none of them is a fault:

- 3 orphaned iSCSI `globalmount` paths that no PersistentVolume owns.
- 3 Jellyfin CIFS media shares. They are `ReadOnlyMany` with the `ro` mount option, by design.

A rule on `== 1` alone matches 7 series today and reports all 6 for ever. The rule with `changes(node_filesystem_readonly[2h]) > 0` matched 0 series after the correction, and matches a volume that was read-write and is now read-only.

NOTE: Do not add an alert on `cnpg_collector_up == 0`. The measurement on 2026-10-12 returned 4 series on a healthy cluster.

## Open item

3 `globalmount` paths on `talos-3xg-mwx`, `talos-0wq-zph` and `talos-ako-s53` are read-only and no PersistentVolume owns them. They hold a device each. They are left from volumes that are gone. They have no effect on a workload. Remove them from the node.

## Recurrence on 2026-10-13

2 more volumes went read-only after the first correction: `soiree-pg-2` at 23:44 UTC on 2026-10-12, and `soiree-pg-3`. An operator found them on 2026-10-13. `soiree-pg` came through the first event with 3 of 3 instances ready, so a volume can turn read-only hours after the storage returns. Check each cluster again on the day after an event of this kind.

The correction is the same. An operator deleted the 2 replicas and each came back ready in under 60 seconds with 0 restarts. The primary `soiree-pg-1` was not affected and stayed up, so the application kept its database.

The alert did its job and then undid it:

| Time (UTC) | State |
|---|---|
| 10-12 23:44 | The mount turns read-only. |
| 10-12 23:45 | `VolumeRemountedReadOnly` goes to pending. |
| 10-12 23:50 | The alert fires, 6 minutes after the fault. |
| 10-13 01:44 | The alert clears. The volume is still read-only. |
| 10-13 14:04 | `KubePodCrashLooping` raises the fault, 14 hours after 23:44. |

The clear at 01:44 is 23:44 plus the 2 hour window, which is the proof that the window caused it. Read the series at a step of 1 minute. A step of 5 minutes puts the fire at 23:49 and the clear at 01:39, and those 2 times fit no window.

`changes(node_filesystem_readonly[2h])` stops matching 2 hours after the transition, so the rule cleared itself while the fault remained. An alert that clears while the fault remains is worse than no alert, because the record says the cluster recovered.

The rule now has `keep_firing_for: 24h`. It holds the alert for 24 hours after the expression stops matching, which covers a fault that starts at night.

CAUTION: `keep_firing_for` does not read the repair. The expression stops matching both when the volume is mounted read-write again and when the 2 hour window expires, so the alert goes on firing for up to 24 hours after an operator repairs the volume. Read `node_filesystem_readonly` for the mount to tell the 2 apart. A volume that turns read-only again inside those 24 hours sends no new notification, because the alert is already firing.

CAUTION: After 24 hours the alert clears, even when the volume is still read-only. Both limits come from the same guard, and the guard is only needed because the orphaned globalmounts read 1 for ever. Remove them from the nodes, then alert on `node_filesystem_readonly == 1` alone. That state ends when the repair ends it, and at no other time.

## Evidence

- Instance manager log of `gitlab-pg-1`: `open /var/lib/postgresql/data/pgdata/pg_wal/_cnpg_probe_Gpzt: read-only file system`. The same line for `openproject-pg-2`.
- Operator log for `gitlab-pg-2`: `FATAL: could not open file "base/5/2601": Read-only file system (SQLSTATE 42501)`.
- `gitlab-pg` status: `danglingPVC: [gitlab-pg-1, gitlab-pg-1-wal, gitlab-pg-3, gitlab-pg-3-wal]`, `ConsistentSystemID: False`.
- `gitlab-pg-2` before the delete: `ready=True`, `restarts=0`, age 17 days.
- After the correction, all 4 CNPG clusters report `Cluster in healthy state` and every pod in the cluster is ready.
- Jellyfin ran through the event: 1 of 1 ready, 0 restarts, age 6 days.
