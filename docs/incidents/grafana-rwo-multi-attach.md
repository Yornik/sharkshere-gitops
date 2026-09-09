# Grafana rollout stopped on a ReadWriteOnce volume

**Date:** not recorded
**Component:** `kube-prometheus-stack` Application, Grafana Deployment
**Severity:** rollout stopped, old pod kept serving

## Effect

A Grafana update did not complete. The new pod stayed in a pending state on a second node. The old pod kept running.

## Cause

Grafana has one persistent volume on the `truenas-ssd` storage class. The access mode is ReadWriteOnce. Only one node can attach the volume at a time.

The chart default rollout strategy is RollingUpdate with a surge of one pod. The scheduler put the new pod on a different node. That node could not attach the volume. The event was `Multi-Attach error`. The old pod held the volume and never stopped.

## Correction

Set the rollout strategy so that no surge pod is created:

```yaml
grafana:
  deploymentStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 0
```

CAUTION: The chart key is `deploymentStrategy` at the top level of the Grafana values. The key `deployment.strategy` is not a chart key. The chart ignores it and gives no error.

## Prevention

Every single-replica workload on a ReadWriteOnce volume needs a strategy that stops the old pod first. Use `maxSurge: 0` or `Recreate`. See the Valkey incident of 2026-09-08 for the same failure on a different chart.

## Evidence

- `apps/values.yaml`, comment above `grafana.deploymentStrategy`.
