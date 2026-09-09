# Valkey rollout stopped on a ReadWriteOnce volume, then the correction was rejected

**Date:** 2026-09-08, follow-up 2026-09-09
**Component:** `gitlab-valkey` Application, chart `valkey` 0.11.0 to 0.12.0, image 9.1.1 to 9.1.2
**Severity:** rollout stopped for 11 hours, old pod kept serving, GitLab stayed up

## Effect

After the Renovate merge, ArgoCD showed the Application as Synced and Progressing. It stayed in that state. The new pod was in `Init:0/1` on node `talos-3xg-mwx`. The old pod was Running on node `talos-0wq-zph`.

GitLab kept its connection to the old pod. There was no user-facing effect.

## Cause

Valkey has one persistent volume on the `truenas-ssd-iscsi` storage class. The access mode is ReadWriteOnce.

The chart default rollout strategy is RollingUpdate with `maxSurge: 25%`. For one replica, that is one surge pod. The scheduler put the new pod on a different node. The event on the new pod was:

```
FailedAttachVolume  Waiting for detach for volume "pvc-273326ce-..."
                    Volume is already used by pod(s) gitlab-valkey-64df575f4c-t8tgz
```

The old pod held the volume. The rollout could not continue.

## Correction, part 1 (in git)

Chart 0.12.0 has a top-level value `deploymentStrategy` with the allowed values `RollingUpdate` and `Recreate`. Set it to `Recreate` in `apps/values.yaml`. Pull request #456 carried the change. CI rendered the chart and confirmed `spec.strategy.type: Recreate` on the Deployment.

## Correction, part 2 (on the cluster)

After the merge, ArgoCD could not apply the change. The Application went to Sync `Unknown` and Health `Degraded` with this condition:

```
Deployment.apps "gitlab-valkey" is invalid:
spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy `type` is 'Recreate'
```

The chart renders only `strategy.type`. The live Deployment still had the `rollingUpdate` block from the old strategy. The `managedFields` showed those fields as owned by `argocd-controller` with operation `Update`. Server-side apply from the same manager with operation `Apply` does not remove fields that a different operation owns. The API server then rejected the object.

One patch removed the old block and set the type:

```sh
kubectl -n gitlab patch deployment gitlab-valkey --type=json \
  -p='[{"op":"remove","path":"/spec/strategy/rollingUpdate"},
       {"op":"replace","path":"/spec/strategy/type","value":"Recreate"}]'
```

The Deployment controller then stopped the old pod first. The volume detached. The new pod became Ready in less than five seconds. ArgoCD reported Synced and Healthy within ten seconds. GitLab stayed Healthy.

## Prevention

- Every single-replica workload on a ReadWriteOnce volume needs `Recreate` or `maxSurge: 0`. See the Grafana incident for the same failure.
- When a chart switches `strategy.type` to `Recreate` but does not render `rollingUpdate: null`, expect this API server error on a live object that was created with RollingUpdate. Clear the `rollingUpdate` block one time by hand, or make the chart render the field.

## Evidence

- `apps/values.yaml`, comment above `deploymentStrategy` in the `gitlab-valkey` values.
- Pull request #456 in this repository.
