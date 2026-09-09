# Incidents

This directory keeps one file for each incident or each significant finding on the cluster.

The write-ups follow a fixed structure: Date, Effect, Cause, Correction, Prevention, Evidence. Sentences are short. Each sentence gives one fact. The source of each write-up is a comment in `apps/values.yaml` or a change that an operator made and recorded.

| Date | File | Effect |
|---|---|---|
| 2026-07-10 | [openproject-seeder-job-immutable.md](2026-07-10-openproject-seeder-job-immutable.md) | OpenProject was down after a chart update |
| 2026-07-10 | [gitlab-backup-pg-dump-version.md](2026-07-10-gitlab-backup-pg-dump-version.md) | GitLab backup job could not dump the database |
| 2026-07-10 | [loki-chunks-cache-oversized.md](2026-07-10-loki-chunks-cache-oversized.md) | Loki reserved 9.8 GiB of memory for a cache with a 0.3 % hit rate |
| not recorded | [grafana-rwo-multi-attach.md](grafana-rwo-multi-attach.md) | Grafana rollout stopped on a volume that only one node can attach |
| 2026-09-08 | [gitlab-valkey-rollingupdate-multi-attach.md](2026-09-08-gitlab-valkey-rollingupdate-multi-attach.md) | Valkey rollout stopped on a volume that only one node can attach, then the correction was rejected by the API server |

## How to add an incident

1. Copy the structure of an existing file.
2. Name the file `YYYY-MM-DD-<short-name>.md`. If the date is not known, omit the date prefix.
3. Add one row to the table above.
4. Put the correction in the manifest as a comment. Point the comment to this directory.
