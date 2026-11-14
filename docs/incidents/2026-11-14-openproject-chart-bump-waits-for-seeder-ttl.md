# OpenProject chart updates wait up to a day behind the seeder Job

**Date:** 2026-11-14
**Component:** `openproject` Application, chart `openproject`, the seeder Job `openproject-seeder-1`
**Severity:** low. No outage. Each chart update reached the cluster 3.5 to 25 hours after its merge, and nothing reported the wait.

## Effect

Chart 13.17.4 merged with #666 on 2026-11-13 at 22:40 UTC. At 23:46 UTC the `openproject` Application turned to sync status `Unknown` with this condition:

```
ComparisonError: Failed to compare desired state to live state: failed to calculate diff:
error calculating server side diff: serverSideDiff error: error running server side apply
in dryrun mode for resource Job/openproject-seeder-1: Job.batch "openproject-seeder-1" is
invalid: spec.template: Invalid value: ... field is immutable
```

On 2026-11-14 at 05:50 UTC the Application still ran chart 13.17.3. The pods ran OpenProject 17.9.7 and were Healthy. The Application synced nothing else in that time.

It is not the first time. Every chart update since at least 2026-09-16 waited the same way. Each one reached the cluster in the evening, between 18:32 and 21:18 UTC, whatever the time of its merge:

| Chart | On `main` (UTC) | Synced (UTC) | Wait |
|---|---|---|---|
| 13.12.0 | 2026-09-16 17:07 | 2026-09-17 18:32 | 25 h |
| 13.13.1 | 2026-10-13 11:53 | 2026-10-13 20:43 | 9 h |
| 13.14.0 | 2026-10-16 12:38 | 2026-10-16 20:47 | 8 h |
| 13.15.1 | 2026-10-20 11:42 | 2026-10-20 20:52 | 9 h |
| 13.16.0 | 2026-10-26 17:35 | 2026-10-26 20:59 | 3.5 h |
| 13.17.0 | 2026-10-29 17:16 | 2026-10-29 21:04 | 4 h |
| 13.17.1 | 2026-11-01 17:24 | 2026-11-01 21:07 | 4 h |
| 13.17.4 | 2026-11-13 22:40 | not before 2026-11-14 21:22 | about 23 h |

Chart 13.11.0 synced 12 minutes after its merge, on 2026-09-08 at 20:56 UTC. Its merge fell inside the evening window.

## Cause

Three settings meet:

1. ArgoCD computes each diff with a server-side dry-run apply. `controller.diff.server.side` is `"true"` in `bootstrap/argocd/argocd-cmd-params-cm-patch.yaml` since 2026-04-30 (#288).
2. Each chart update changes the template of the seeder Job, at least its label `helm.sh/chart`. A Job template is immutable. The dry run of the new template against the live Job fails, so ArgoCD cannot compute the diff. With no diff there is no sync, and the sync option `Force=true,Replace=true` on the Job never runs. That option came on 2026-07-10 (commit `4536a19`), after [`2026-07-10-openproject-seeder-job-immutable.md`](2026-07-10-openproject-seeder-job-immutable.md).
3. The seeder Job has `ttlSecondsAfterFinished: 86400`. Kubernetes deletes the Job 24 hours after it ends. ArgoCD sees it missing and creates it again (self-heal), so the seeder runs about once a day, in the evening.

While no Job exists, the dry run is a create, and it works. ArgoCD then syncs the chart update. That is the only moment a chart update can pass, and it explains the evening times in the table.

The window moves later each time by the run time of the seeder, about 1 minute, plus the delay before ArgoCD notices the missing Job. The last run before #666 started on 2026-11-13 at 21:21:21 UTC and ended at 21:22:26 UTC.

NOTE: A self-heal that creates only the Job is a partial sync. ArgoCD keeps no history entry for it, so the history of the Application shows only the chart updates.

## Correction

The `openproject` Application gets the annotation `argocd.argoproj.io/compare-options: ServerSideDiff=false` in `apps/values.yaml` (#675). ArgoCD then computes its diff on the client side.

- The client-side diff does not send the immutable template to the API server. It shows the Job as `OutOfSync`, and the sync replaces the Job with `Force=true,Replace=true`.
- A chart update then syncs within minutes of its merge, and the seeder runs once for it.
- The other Applications keep the server-side diff. It was turned on for stale schemas of operator CRDs, such as `Prometheus`. The OpenProject chart renders only core Kubernetes objects.

Without #675, chart 13.17.4 syncs by itself at the next window, after the Job of 2026-11-13 expires at about 21:22 UTC on 2026-11-14.

## Prevention

- A `ComparisonError` stops all syncs of its Application, but the Application stays Healthy. No alert fires on sync status `Unknown`. The same gap hides any other Application with a resource that cannot change in place.
- After a chart update with a Job, read the sync status, not only the health:

```bash
kubectl -n argocd get application openproject -o jsonpath='{.status.sync.status} {.status.sync.revision}{"\n"}'
```

Expected result: `Synced` and the new chart version, a few minutes after the merge.

- The seeder Job still runs once a day: the 24-hour TTL deletes it and the self-heal creates it again. Its migrations and seed data are idempotent. This write-up does not change that.

## Evidence

- The condition of the `openproject` Application on 2026-11-14 at 05:50 UTC, quoted under Effect. The last sync used 13.17.3.
- The live Job: `helm.sh/chart: openproject-13.17.3` in its template, `ttlSecondsAfterFinished: 86400`, start 2026-11-13 21:21:21 UTC, end 21:22:26 UTC. The last operation of the Application, on 2026-11-13 at 21:21 UTC, says `job.batch/openproject-seeder-1 created`, 2 days after the last chart sync.
- The history of the Application: the sync times in the table, ids 10 to 17.
- `git log` of `main`: the merge times in the table, and #288 for `controller.diff.server.side`.
- `apps/values.yaml`, comment above the annotation of `openproject`.
