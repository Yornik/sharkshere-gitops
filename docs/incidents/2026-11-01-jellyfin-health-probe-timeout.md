# Jellyfin answered "no available server" while it rescanned its libraries

**Date:** 2026-11-01 18:43 UTC to 18:46 UTC
**Component:** `jellyfin` Deployment (`manifests/jellyfin/deployment.yaml`)
**Severity:** 2 minutes without Jellyfin, and 1 container restart. No data lost

## Effect

Clients of `jelly.yornik.eu` got "no available server" for about 2 minutes. The Service `jellyfin` had no endpoints from 18:43:50 to 18:45:50. The container was then killed and restarted (exit 137, 1 restart). Jellyfin was ready again at 18:45:42 and served.

The pod, the config volume and the media mounts were not damaged.

## Cause

An operator deleted the `music` library in the Jellyfin interface at 18:42. Jellyfin then checked every library again ("Validating media library") and ran its 9 post-scan tasks. The pod used about 3 of its 4 CPU cores (`kubectl top`: 3075m).

Both probes call `/health` with the default `timeoutSeconds: 1`. Under that load Jellyfin did not answer in 1 second. The probes failed with `context deadline exceeded`.

| Probe | Effect of the failures |
|---|---|
| Readiness (every 10 s, 3 failures) | The pod left the Service. Traefik had no server. |
| Liveness (every 30 s, 3 failures) | Kubelet killed the container after about 90 seconds. |

The process was busy, not broken. The kill made the outage longer and cut the scan off.

NOTE: The earlier library scan of the same day (17:28 to 17:42 UTC, 13 minutes) did not take the pod out of the Service. `kube_pod_status_ready` shows 1 gap in the last 4 hours, the one above. A scan alone does not always starve `/health`.

## Correction

1. Nothing was needed for the recovery. Kubelet restarted the container and Jellyfin came back by itself.
2. Set `timeoutSeconds: 30` on the liveness probe and on the readiness probe in `manifests/jellyfin/deployment.yaml`. A busy Jellyfin that answers within 30 seconds stays in the Service and is not killed.
3. Remove the `music` volume, the mount `/media/music`, the PersistentVolumeClaim `jellyfin-music` and the PersistentVolume `jellyfin-music` (`pv-music.yaml`, `pvc-music.yaml`, and their lines in `kustomization.yaml`). The library was deleted and nothing else used the mount. ArgoCD prunes the 2 objects. The PV had `persistentVolumeReclaimPolicy: Retain` and an SMB source, so the files on the NAS (`shared_evreyone/music`) are not touched. To get the library back, restore these files from git history.

## Prevention

The change has 2 costs:

| Cost | Detail |
|---|---|
| A hung process is found later | A Jellyfin that does not answer at all is killed after 3 probes of up to 30 seconds each, which is a few minutes and not 90 seconds. |
| A busy Jellyfin stays in the Service | During a scan the pages can be slow. Before the change they failed with "no available server". |

Open item: the time that `/health` takes during a scan was not measured. If it is above 30 seconds, the probes still fail. Measure it during the next library scan, and raise the timeout or the `failureThreshold` of the liveness probe if needed.

## Evidence

- `kubectl -n jellyfin get events`: `Liveness probe failed: Get "http://10.244.3.161:8096/health": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`, and the same for the readiness probe.
- `kubectl -n jellyfin get endpoints jellyfin`: empty at 18:44:35. `10.244.3.161:8096` at 18:46:07.
- Jellyfin log: 18:42:32 `Stopping directory watching for path /media/music`, 18:43:25 `Validating media library`, 18:44:22 `Running 9 post-scan task(s)`.
- Container CPU from Prometheus (`container_cpu_usage_seconds_total`, 2 minute rate): 0.00 until 18:40, 0.13 at 18:42, 2.22 at 18:44.
- Pod status: restart count 1, last state `Error`, exit code 137, restart at 18:45:31.
- `kube_pod_status_ready{condition="true"}` at a step of 30 seconds: absent from 18:43:50 to 18:45:50.
- Probe settings before the change: `timeoutSeconds: 1`, `failureThreshold: 3` on both.
