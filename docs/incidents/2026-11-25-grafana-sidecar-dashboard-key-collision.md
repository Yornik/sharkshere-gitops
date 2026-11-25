# Two dashboards share one sidecar file: one silently disappears

**Date:** 2026-11-25 (found on the live cluster, corrected the same day)
**Component:** Grafana dashboard sidecar (`grafana-sc-dashboard`), ConfigMaps `homeconnect-dashboard` and `tibber-dashboard`
**Severity:** one dashboard invisible in Grafana. No data lost, no alert involved, no scrape affected.

## Effect

Minutes after the `siemens-home-connect-exporter` Application went Synced
and Healthy, the Home Connect dashboard did not exist in Grafana. The
dashboards search returned nothing. The ConfigMap was present in
`monitoring` and carried the `grafana_dashboard: '1'` label, so every
repo check passed and ArgoCD reported health.

## Cause

The sidecar writes one file per ConfigMap data key: the key becomes the
file name under `/tmp/dashboards`. The new dashboard copied the data key
`dashboard.json` from `tibber-dashboard`. Both ConfigMaps then wrote the
same path each poll cycle (about every 60 seconds), each write replacing
the other's content. The Grafana file provisioning imports one dashboard per file. Only the
writer that came last in a cycle existed at any moment. The tibber
dashboard won the interleaving that day.

Evidence: the sidecar log shows two `Writing /tmp/dashboards/dashboard.json`
lines per poll cycle from 17:34 UTC. Every other dashboard in the cluster
already used a unique key: `mazda6e.json`, `shelly.json`,
`shelly-control.json`, `dirigera-air-quality.json`,
`secure-file-share.json`. The tibber key was unique only until a second
ConfigMap copied it.

## Correction

PR #728 renames both data keys: `homeconnect.json` for the Home Connect
dashboard, `tibber.json` for the tibber dashboard. No ConfigMap keeps the
generic key `dashboard.json`, so the path has no writer left and no
future copy can collide with it. The ConfigMap header comments state the
convention and point to this report. The same PR pins the data source
variable current to the documented house form (`selected: true`).

Note for the rollout: the sidecar does not delete a file whose writer
disappears. Until the Grafana pod restarts once, a stale
`/tmp/dashboards/dashboard.json` may linger with frozen tibber content.
Both live dashboards carry unique uids, so the provisioning keeps the
right objects either way; a pod restart clears the stale file.

## Detection gap

No repo check can catch this class. A duplicate data key across two
ConfigMaps is valid Kubernetes. The JSON parses, the label is right, and
ArgoCD reports Healthy. The check that works is a convention check
before copying a dashboard. Name the data key after the dashboard. Grep
the repo for the planned key first. The convention lives in the skill
reference `grafana-dashboards.md`.
