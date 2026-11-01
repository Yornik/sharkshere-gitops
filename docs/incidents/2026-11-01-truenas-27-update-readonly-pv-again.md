# The TrueNAS 27 update turned the iSCSI volumes read-only again, and the same repair fixed them

**Date:** 2026-11-01
**Component:** `truenas-ssd-iscsi` volumes; the `gitlab-pg`, `openproject-pg` and `shared-pg` CNPG clusters
**Severity:** the 3 clusters served no query for about 10 to 17 minutes. No data loss was seen. The repair took about 9 minutes

## Effect

An operator updated the NAS from TrueNAS 25.10.7 to 27.0.0-RC.1. The NAS stopped answering on every service port between 00:05:23 UTC and 00:06:40 UTC. The services were back at 00:09:51 UTC.

This is the second time. See [the incident of 2026-10-12](2026-10-12-truenas-update-readonly-pv-remount.md).

| Cluster | State at 00:10 UTC | Healthy again |
|---|---|---|
| `openproject-pg` | 0 of 3 ready. Each instance restarted 3 to 6 times. | about 00:16 |
| `shared-pg` | 0 of 3 ready. | about 00:18 |
| `gitlab-pg` | 1 of 3 ready, and that one served no query. | 00:23 |
| `soiree-pg` | 3 of 3 ready. Not affected. | n/a |

The NFS volumes did not need a repair. Radarr, Sonarr and Prowlarr restarted 4 to 6 times each and were ready again by 00:19 UTC. Vaultwarden, Vikunja and Prometheus restarted once. The hourly `recyclarr` job at 00:17 UTC failed, and ArgoCD showed `recyclarr` as Degraded at 00:25 UTC. The next job runs at 01:17 UTC.

WARNING: `gitlab-pg-3` reported `Ready` with 0 restarts while its Postgres could not write. Its log held 71 read-only lines in 2 minutes and 789 in 5 minutes. The readiness probe proves that the process accepts a connection. It does not prove that the process can write a file.

## Cause

The update restarted the NAS while Postgres was writing. The iSCSI targets went away. The volumes returned an I/O error. ext4 mounts with `errors=remount-ro`, so the kernel made each filesystem read-only. This is the same mechanism as on 2026-10-12.

The sessions on the nodes wait `Recovery Timeout: 120` seconds for the target to return. Then open-iscsi fails the queued I/O up to the filesystem. The NAS refused every service port from 00:06:40 UTC and had them open again before 00:09:51 UTC, which is more than 3 minutes and longer than the timer. An outage shorter than 120 seconds would not have broken these mounts.

A read-only ext4 does not become read-write again by itself. Postgres cannot write, so it exits. The pod restarts, finds the same read-only mount, and exits again.

Read-only lines were in the log of 8 instances at 00:10:34 UTC. The driver change of the same night, [pull request 624](https://github.com/Yornik/sharkshere-gitops/pull/624), merged at 00:12:13 UTC, so it is not the cause.

The state of `gitlab-pg` was the trap of the first incident:

- `gitlab-pg-2`, the primary, was `1/2` and its Postgres socket did not answer. The log said `This is an old primary instance, waiting for the switchover to finish`.
- `gitlab-pg-1`, the new primary, crash-looped on the read-only mount.
- `gitlab-pg-3` was `2/2` and broken.

After the delete of `gitlab-pg-1` and `gitlab-pg-2`, CNPG held their 4 PVCs as `danglingPVC` and built no pod. The cluster phase was `Instance Status Extraction Error: HTTP communication issue`. CNPG builds nothing while the ready-looking instance is present.

## Correction

An operator deleted the pods one at a time. The kubelet unmounts the volume and mounts it again, and the new mount is read-write. Each pod was ready in 25 to 45 seconds with 0 read-only lines.

1. `openproject-pg`: `pg-3` at 00:14:44, `pg-1`, `pg-2`. The primary moved to `openproject-pg-3`.
2. `shared-pg`: the replicas first, `pg-2` at 00:16:34, then `pg-3`, then the primary `pg-1`. The primary moved to `shared-pg-2`.
3. `gitlab-pg`: `pg-1` at 00:18:25, then `pg-2`, then `pg-3` last, at 00:22:27, after its log was read. The cluster was healthy at 00:23:24 with `gitlab-pg-2` as primary.

```bash
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-1
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-2
kubectl --context yornik-sharkshere -n gitlab logs gitlab-pg-3 -c postgres --since=5m | grep -c -i 'read-only file system'
kubectl --context yornik-sharkshere -n gitlab delete pod gitlab-pg-3
```

CAUTION: Do not wait for a deleted pod to become `2/2` before the next delete in `gitlab-pg`. Until the broken instance that looks ready is gone, CNPG builds no pod, so the wait always runs out. A script that waited 180 seconds per pod lost 3 minutes this way, and its next step would have deleted `gitlab-pg-3` twice. Delete the instances that crash-loop, read the log of the one that reports `Ready`, and delete it last.

Nothing else needed a delete. After the databases returned, the OpenProject worker and the GitLab web service recovered on their own.

## Prevention

1. The alert worked this time. `VolumeRemountedReadOnly` fired 12 times, from 00:11:07 to 00:11:37 UTC. That is about 5 minutes after the NAS stopped and 3 minutes before the first repair. It names the mount paths, not the pods.
2. Stop every iSCSI client before a NAS restart. This was not done. See "The next NAS update" below.
3. After every NAS restart, scan the log of every CNPG instance. Kubernetes `Ready` is not enough:

```bash
kubectl --context yornik-sharkshere get pods -A -l cnpg.io/cluster \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' |
while read ns p; do
  echo "$ns/$p read-only lines: $(kubectl --context yornik-sharkshere -n "$ns" logs "$p" -c postgres --since=10m 2>/dev/null | grep -c -i 'read-only file system')"
done
```

On 2026-11-01 at 00:25 UTC this printed 0 for all 12 instances.

4. Do not run `zpool upgrade` after a TrueNAS update. Both pools show `PoolUpgraded` notices. Enabling the new feature flags cannot be undone, and a boot environment does not restore a data pool.
5. `soiree-pg` and the NFS volumes came through untouched or recovered alone. Both write little. The volumes that write the most are the ones that break.

## The next NAS update

Stopping the databases first is the right fix, and it is not enough alone. A pod that is gone has unmounted its volume and logged out of the target. The kubelet unmounts the volume and the driver logs out of the target after the containers stop. When the NAS restarts, no session exists, so no I/O fails and ext4 never goes read-only. This is the same path that fixed each volume today: the pod delete remounted a clean filesystem.

CNPG is 4 of the 8 groups that mount an iSCSI volume. Read on 2026-11-01:

| Namespace | Mounts an iSCSI volume |
|---|---|
| `gitlab` | `gitlab-pg` (3 instances), `gitlab-valkey`, `gitlab-gitaly` |
| `openproject` | `openproject-pg` (3 instances), `openproject-web`, `openproject-worker-default`, `openproject-hocuspocus`, the seeder Job |
| `shared-pg` | `shared-pg` (3 instances) |
| `soiree` | `soiree-pg` (3 instances) |

The OpenProject pods hold generic ephemeral volumes on the iSCSI class. `gitlab-gitaly` and `gitlab-valkey` showed no read-only line today because they write little. That is luck, not safety.

Use hibernation for CNPG, not fencing. The CNPG documentation (version 1.30.1 runs here) says hibernation "will delete the primary Pod and then the replica Pods, avoiding switchover, to ensure the replicas are kept in sync", and that the PVCs are retained. Fencing keeps the pod running and the volume mounted, so it does not help.

### Before

1. Wait for the next scheduled backup of the 4 clusters, every 3 hours, and check that all 4 completed: `kubectl --context yornik-sharkshere get backups.postgresql.cnpg.io -A --sort-by=.metadata.creationTimestamp | tail -8`. One backup can fail on a throttle of the object storage. See the note after the checklist.
2. Pause ArgoCD self-heal, or it puts the replicas back. `root` owns the Application objects and has `selfHeal: true`, so pause `root` first and then each app that you scale:

```bash
kubectl --context yornik-sharkshere -n argocd patch application root --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
```

3. Hibernate the 4 clusters and wait for the condition `cnpg.io/hibernation` to read `True` on each:

```bash
for c in gitlab/gitlab-pg openproject/openproject-pg shared-pg/shared-pg soiree/soiree-pg; do
  kubectl --context yornik-sharkshere -n "${c%/*}" annotate cluster "${c#*/}" --overwrite cnpg.io/hibernation=on
done
```

4. Scale to 0 the other clients: `gitlab-valkey`, `gitlab-gitaly` (StatefulSet), `openproject-web`, `openproject-worker-default`, `openproject-hocuspocus`. Scale the GitLab web service and Sidekiq too, so they do not crash-loop against a database that is off.
5. Do not start before this gate passes. The NAS must report no iSCSI session. On 2026-11-01 it reported 33:

```bash
ssh root@192.168.1.42 'midclt call iscsi.global.sessions | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"'
```

### During

6. Update from the web interface. Do not run `zpool upgrade`. Wait until the `iscsitarget` service reads `RUNNING`.

### After

7. Wake one cluster at a time with `cnpg.io/hibernation=off`. Wait for `Cluster in healthy state`, then run the log scan of Prevention 3. Then scale the other clients up.
8. Re-enable ArgoCD last: `kubectl --context yornik-sharkshere apply -f bootstrap/root-app.yaml`. `root` then restores the auto-sync of the child apps.

The cost is a planned stop of GitLab and OpenProject for the length of the update. Today it was an unplanned stop of 10 to 17 minutes and a hand repair. NFS clients do not need this: they waited and recovered alone. A client that keeps SQLite on NFS (`vikunja`, `gotosocial`) can still be scaled to 0 for the same reason.

If a step is forgotten, the Correction above repairs it.

### Backups before the update

The backups go from the cluster to the Hetzner Object Storage at `nbg1.your-objectstorage.com`. They do not use the NAS, so the update did not cause the `CNPGBackupFailed` alert of 2026-10-31.

That backup of `shared-pg` failed at 12:00 UTC. The log of the barman plugin says `Backup failed uploading backup.info file (An error occurred (SlowDown) when calling the PutObject operation (reached max retries: 4))`. `SlowDown` is the throttle answer of the object storage. The client retried 4 times and gave up after 28 seconds. CNPG does not run a failed Backup again. The next one, at 15:00 UTC, completed, and so did the 18:00, 21:00 and 00:00 runs.

The same answer is not new. In the last 30 days the plugin logs of the 4 clusters hold 38 to 61 `SlowDown` lines each, on 9 days. The two earlier failures of `shared-pg` (2026-10-17 at 12:00 and 2026-10-21 at 03:00) have the same cause, and on both days other clusters failed in the same minute, because the 4 schedules start together. WAL archiving is a separate path and logged no error in the 12:00 to 15:30 window, so the point-in-time range had no hole. `ContinuousArchiving` is `True` on all 4 clusters.

Done the same day, in PR 632 (merged 2026-11-01 18:23 UTC): the 4 schedules start at :00, :10, :20 and :30 (shared-pg, openproject, gitlab, soiree). A backup takes 4 to 30 seconds, so they no longer overlap. This is not proof that `SlowDown` ends: the throttle can also come from other load on the project. Count the `SlowDown` lines and the failed backups again after 30 days.

NOTE: A change of schedule starts a backup at once when the new schedule has a slot between the last run and now. PR 632 said it would not. At the sync, `openproject-pg` (new slot :10) and `gitlab-pg` (new slot :20) each started a backup at 18:23:14 UTC, in the same second, for the slot of 18:10 and 18:20 that they had missed. Both completed in 7 and 18 seconds with no error. `shared-pg` (slot :00) and `soiree-pg` (slot :30) started none. Expect this once after the next change of a schedule, and do not make the change while a backup of that cluster is failing.

### A second layer, not yet done

The 120 second timer is the reason a 3 minute outage breaks the mounts. A longer timer, for example 600 seconds, would make the clients queue the I/O and continue when the NAS returns. The price is that a real NAS failure freezes the pods for 10 minutes before they fail. The driver passes any key that starts with `node-db.` in the node-stage secret to `iscsiadm` (`src/driver/index.js`, `node-db.node.session.timeo.replacement_timeout`). That needs a StorageClass that names such a secret, so it reaches new volumes only, not the 36 that exist. Test it on one new volume before any change.

## Open items

- No restore or point-in-time test was run after the repair. The 4 clusters report a healthy state and `ContinuousArchiving` is `True`.
- The checklist of "The next NAS update" is untested as a whole. Hibernation of a CNPG cluster, the pause of ArgoCD through `root`, and the `bootstrap/root-app.yaml` re-enable were not run. Test the order on `soiree-pg` first.
- Whether ArgoCD keeps the `cnpg.io/hibernation` annotation is unknown. It compares only fields in git, so the annotation should stay. This was not tried.
- The 600 second timer is an idea, not a result.
- The 12 alerts stay in the firing state until the 2 hour window of the rule ends, so Alertmanager may mail them after the repair.

## Evidence

- `gitlab-pg` before the repair: `danglingPVC: [gitlab-pg-1, gitlab-pg-1-wal, gitlab-pg-2, gitlab-pg-2-wal]`, phase `Instance Status Extraction Error: HTTP communication issue`, and `gitlab-pg-3` `2/2` with 789 read-only lines in 5 minutes.
- Log of `gitlab-pg-2`: `This is an old primary instance, waiting for the switchover to finish`.
- Driver Probe of the NFS controller: `ready: true` at 00:05:23 UTC, then `ECONNREFUSED 192.168.1.42:443` from 00:06 UTC.
- Port scan at 00:06:40 UTC: ping answered, ports 22, 80, 443, 2049 and 3260 refused. All 4 open at 00:09:51 UTC.
- Read-only lines at 00:10:34 UTC: `openproject-pg-1/2/3` 3 each, `shared-pg-1` 4, `shared-pg-2/3` 3 each, `gitlab-pg-1` 3, `gitlab-pg-3` 14. `soiree-pg` 0.
- After the repair, 00:23:43 UTC: 185 pods, all ready except the completed ones; the 4 clusters at `3 / 3` ready; 65 of 65 PVCs bound.
- `node_filesystem_readonly == 1` at 00:25 UTC listed only Talos system paths and the 3 Jellyfin CIFS shares, which are read-only by design. No iSCSI mount.
- `VolumeRemountedReadOnly` in `additionalPrometheusRulesMap` in `apps/values.yaml`. `CNPGInstanceNotAnswering` in `manifests/monitoring/prometheusrule-cnpg.yaml`.
