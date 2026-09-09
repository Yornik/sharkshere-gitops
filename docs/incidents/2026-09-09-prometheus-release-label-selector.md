# A monitor without the release label is invisible to Prometheus

**Date:** 2026-09-09 (finding, verified on the live cluster)
**Component:** `kube-prometheus-stack` Application, Prometheus custom resource
**Severity:** no effect today. This is a trap for future work.

## Effect

Prometheus ignores a ServiceMonitor, PodMonitor, PrometheusRule, Probe or ScrapeConfig that does not carry the label `release: kube-prometheus-stack`.

There is no error. The object is created. ArgoCD reports the Application as Synced and Healthy. The target does not appear in Prometheus and the metrics never arrive.

## Cause

The chart sets five values to `true` by default:

```
prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues
prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues
prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues
prometheus.prometheusSpec.probeSelectorNilUsesHelmValues
prometheus.prometheusSpec.scrapeConfigSelectorNilUsesHelmValues
```

With that default, the chart writes a release-scoped selector into the Prometheus custom resource. Each of the five selectors becomes:

```yaml
matchLabels:
  release: kube-prometheus-stack
```

The namespace selector is empty, so Prometheus looks in all namespaces. Only the label decides.

## Correction

Put the label on each monitor that the chart does not create.

For a manifest in this repository, set it in `metadata.labels`:

```yaml
metadata:
  labels:
    release: kube-prometheus-stack
```

For a monitor that another chart creates, use that chart's value for extra labels. The cloudnative-pg operator uses `podMonitorAdditionalLabels`, set in `apps/values.yaml`.

## Prevention

- Add the label when you add a monitor. Do this in the same commit.
- If metrics do not appear, check the label first. Use this command:

```sh
kubectl get servicemonitors,podmonitors,prometheusrules -A \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,RELEASE:.metadata.labels.release'
```

Any row with an empty RELEASE column is invisible to Prometheus.

NOTE: A rejected alternative was to set the five values to `false`, which makes Prometheus accept every monitor in every namespace. The branch `feat/prometheus-select-all` held that change and never reached a pull request. The label is the better option. It is explicit, and it does not silently ingest monitors that a future chart creates.

## Evidence

- Live cluster on 2026-09-09: all five selectors on the Prometheus custom resource read `release: kube-prometheus-stack`. All 12 ServiceMonitors, 4 PodMonitors and 31 PrometheusRules carry the label. Nothing is missed.
- `apps/values.yaml`, `podMonitorAdditionalLabels` in the `cnpg-operator` values.
- `manifests/tibber-exporter/servicemonitor.yaml`, `manifests/dirigera-exporter/servicemonitor.yaml`, `manifests/truenas-monitoring/servicemonitor.yaml`, `manifests/gitlab/podmonitor.yaml`, `manifests/shared-pg/podmonitor.yaml`.
