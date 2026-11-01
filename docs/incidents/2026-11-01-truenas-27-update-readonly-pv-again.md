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
2. Stop the writers before a NAS restart. This was not done. CNPG supports hibernation with the annotation `cnpg.io/hibernation: "on"` on the Cluster, and `"off"` brings the instances back. This write-up did not test it. Test it on `soiree-pg` first.
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

## Open items

- No restore or point-in-time test was run after the repair. The 4 clusters report a healthy state and `ContinuousArchiving` is `True`.
- The hibernation step of Prevention 2 is untested.
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
