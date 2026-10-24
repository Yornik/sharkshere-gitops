# A storage update turned 6 volumes read-only, and the pod that looked healthiest was the most broken

**Date:** 2026-10-12
**Component:** `truenas-ssd-iscsi` volumes; the `gitlab-pg` and `openproject-pg` CNPG clusters
**Severity:** OpenProject down about 5 hours; GitLab accepted connections but served no query for the same time.

## Effect

An operator updated TrueNAS at about 15:16 UTC. Alerts started in the same minute.

| Cluster | State |
|---|---|
| `openproject-pg` | 0 of 3 instances ready. Each pod restarted about 70 times. |
| `gitlab-pg` | 1 of 3 instances ready. The 1 ready instance served no query. |
| `shared-pg` | 3 of 3 ready. The primary was not affected. Postgres did not answer on the 2 replicas from 2026-10-12 15:02 UTC until 2026-10-16 11:12 UTC, which is 3.8 days. |
| `soiree-pg` | 3 of 3 ready. The primary was not affected. Postgres did not answer on `soiree-pg-2` and `soiree-pg-3` from 15:02 UTC until 23:42 UTC. See [the second write-up](2026-10-13-readonly-alert-cleared-while-volume-broken.md). |

Kubernetes reported both `shared-pg` replicas `Ready` for the whole 3.8 days. This file does not record what ended the state on 2026-10-16. See the Evidence section for the measurement.

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

NOTE: An alert on `cnpg_collector_up == 0` is valid. An earlier version of this note advised against it, after a query returned 4 series on clusters that looked healthy. Measured 2026-10-23 over 30 days: the metric read 0 for 10 minutes or more on 5 instances only, and all 5 were broken on 2026-10-12. The 2 `shared-pg` replicas stayed in that state until 2026-10-16 11:12 UTC, which is 3.8 days. Kubernetes reported them Ready the whole time. The alert `CNPGInstanceNotAnswering` in `manifests/monitoring/prometheusrule-cnpg.yaml` uses this metric.

## Open item

2 `globalmount` paths are read-only and no PersistentVolume owns them, measured 2026-10-13:

| Node | Device | Volume handle |
|---|---|---|
| `talos-3xg-mwx` | `/dev/sdb` | `4ae9607f...` |
| `talos-ako-s53` | `/dev/sdb` | `3d144e6b...` |

They are left from volumes that are gone. They have no effect on a workload. Remove them from the node.

NOTE: A third path on `talos-0wq-zph` was read-only on 2026-10-12 and is read-write on 2026-10-13. No PersistentVolume owns it either. It changed when kubelet mounted a volume on that node again. A repair on a node can therefore clear an orphaned mount on the same node.

These paths are the reason the `VolumeRemountedReadOnly` rule reads the change and not the state. Remove them, and the rule reads `node_filesystem_readonly == 1` alone. See [`2026-10-13-readonly-alert-cleared-while-volume-broken.md`](2026-10-13-readonly-alert-cleared-while-volume-broken.md).

## Evidence

- Instance manager log of `gitlab-pg-1`: `open /var/lib/postgresql/data/pgdata/pg_wal/_cnpg_probe_Gpzt: read-only file system`. The same line for `openproject-pg-2`.
- Operator log for `gitlab-pg-2`: `FATAL: could not open file "base/5/2601": Read-only file system (SQLSTATE 42501)`.
- `gitlab-pg` status: `danglingPVC: [gitlab-pg-1, gitlab-pg-1-wal, gitlab-pg-3, gitlab-pg-3-wal]`, `ConsistentSystemID: False`.
- `gitlab-pg-2` before the delete: `ready=True`, `restarts=0`, age 17 days.
- After the correction, all 4 CNPG clusters report `Cluster in healthy state` and every pod in the cluster is ready.
- Jellyfin ran through the event: 1 of 1 ready, 0 restarts, age 6 days.
- Prometheus, read 2026-10-23: `cnpg_collector_up` read 0 from 2026-10-12 15:02 UTC on 5 instances. `gitlab-pg-2` recovered at 21:47, `soiree-pg-2` and `soiree-pg-3` at 23:42, and `shared-pg-1` and `shared-pg-3` on 2026-10-16 at 11:12. On 2026-10-14 12:00 UTC the 2 `shared-pg` replicas exported 44 `cnpg_*` series each, against 460 on the healthy primary, and the pods read Ready.
