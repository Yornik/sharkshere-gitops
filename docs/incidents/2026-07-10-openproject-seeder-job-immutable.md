# OpenProject down after chart update (immutable seeder Job)

**Date:** 2026-07-10
**Component:** `openproject` Application, chart `openproject`, image 17.5.1 to 17.6.0
**Severity:** service down

## Effect

OpenProject at `plan.yornik.eu` was not available. The `web` and `worker` pods restarted in a loop. The error in the logs was `PendingMigrationError`.

## Cause

The chart runs database migrations in a Kubernetes Job named the seeder Job. A Job template is immutable. The chart update changed the image tag in that template.

ArgoCD applies changes with a PATCH by default. The API server rejected the PATCH with `spec.template: Invalid value`. The migration never ran. The application pods started against an old database schema and stopped.

## Correction

Add two sync options to the seeder Job through the chart value `seederJob.annotations`:

```yaml
argocd.argoproj.io/sync-options: Force=true,Replace=true
```

`Replace=true` makes ArgoCD delete and create the Job when the Job drifts. `Force=true` allows the replacement of the immutable field.

## Prevention

The annotation stays in `apps/values.yaml`. Each future chart update that changes the Job image re-runs the seeder Job one time. The seeder Job is idempotent. It runs migrations and seed data.

CAUTION: Any sync that changes the Job re-runs the seeder Job. This includes the merge of the annotation itself.

## Evidence

- `apps/values.yaml`, comment above `seederJob.annotations`.
