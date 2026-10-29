# The Postgres image of each CNPG cluster stayed at the version of its creation day

**Date:** 2026-10-29
**Component:** `gitlab-pg`, `openproject-pg`, `shared-pg`, `soiree-pg` (CNPG `Cluster`), `renovate.json5`
**Severity:** update gap, no user-facing effect

## Effect

The 4 Postgres clusters ran old minor releases of Postgres 18. Renovate opened no pull request for them. ArgoCD showed every cluster as synced.

| Cluster | Created | Image on 2026-10-29 |
|---|---|---|
| `shared-pg` | 2026-05-23 | `18.3-system-trixie` |
| `openproject-pg` | 2026-05-23 | `18.3-system-trixie` |
| `gitlab-pg` | 2026-05-23 | `18.3-system-trixie` |
| `soiree-pg` | 2026-09-18 | `18.4-system-trixie` |

The newest Postgres 18 image of CNPG was `18.6-system-trixie`. The operator itself, 1.30.1, already used `18.6-system-trixie` as its default.

Nothing reported the gap. An operator found it on 2026-10-29: the Radarr status page read `postgreSQL 18.3`, and the operator asked why Renovate had not bumped it.

## Cause

No `cluster.yaml` set `spec.imageName`. The CNPG admission webhook fills in an empty `imageName` when a `Cluster` is created. It writes the default image of the operator that runs at that moment.

That value then stays in the spec. A later operator upgrade brings a newer default, but it does not change a `Cluster` that exists already. So each cluster kept the default of its creation day: 18.3 for the 3 clusters from May, 18.4 for `soiree-pg` from September.

Git and the 2 tools that read git therefore missed the image.

- ArgoCD compares only the fields in git. `imageName` was not in git, so the cluster showed as synced.
- Renovate had nothing to read. Its `kubernetes` manager also reads only `image:` keys, and a CNPG `Cluster` names its image in `imageName:`. A pin in git would not have been found either.

This is the same fault class as [renovate-frozen-by-tag-suffix.md](2026-10-21-renovate-frozen-by-tag-suffix.md): a version that Renovate does not see, and no signal for it.

## Correction

1. Set `imageName: ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie` in the 4 `cluster.yaml` files. Git now names the image, and ArgoCD owns the field.
2. Add a regex `customManager` in `renovate.json5` for `imageName:` in `manifests/*/cluster.yaml`, with the docker datasource. The `-system-trixie` suffix stays the same between releases, so the default docker versioning reads it.
3. Add a `packageRule` for a major bump of `ghcr.io/cloudnative-pg/postgresql`. It adds a note to the pull request. A minor bump keeps the automerge of the docker rule.

The merge of the correction restarts each cluster once. CNPG updates the replicas one at a time and then restarts the primary in place (`primaryUpdateMethod: restart`). Writes stop for a few seconds on each cluster.

## Upgrades from now on

A **minor** bump, for example 18.6 to 18.7, keeps the data files. Postgres keeps its statistics, so it needs no ANALYZE. Read the release notes all the same: a minor release sometimes asks for a `REINDEX` of an index type.

A **major** bump, for example 18 to 19, is an offline in-place upgrade from CNPG 1.26 on:

1. CNPG stops every instance of the cluster.
2. A Job runs `pg_upgrade` on the primary volume.
3. CNPG recreates the replicas from the new primary.

CNPG does not run ANALYZE after it. From Postgres 18, `pg_upgrade` keeps most optimizer statistics, but not extended statistics. Run this in the primary after each upgrade:

```bash
vacuumdb --all --analyze-in-stages --missing-stats-only
```

Then take a new base backup. A point-in-time recovery cannot cross a major version, so the older backups cannot restore to a time after the upgrade.

CAUTION: the upgrade needs the same operating system in the old and the new image. Keep the `-system-trixie` suffix.

## Prevention

1. Set `imageName` on each new CNPG `Cluster`. An empty field freezes the image at the day of creation.
2. The same holds for each operator that fills in a default at creation. A field that the API server writes and git does not name never changes, and no tool reports it.
3. The checks in [renovate-frozen-by-tag-suffix.md](2026-10-21-renovate-frozen-by-tag-suffix.md) also cover this case. Compare the running image of each workload with the newest tag upstream.

## Evidence

- `kubectl get clusters.postgresql.cnpg.io -A` on 2026-10-29: `spec.imageName` and `status.image` per cluster, as in the table above. No `cluster.yaml` in git set `imageName`.
- The log of the operator at its start on 2026-10-26: `"operatorImageName":"ghcr.io/cloudnative-pg/cloudnative-pg:1.30.1","postgresImageName":"ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie"`.
- The tag list of `ghcr.io/cloudnative-pg/postgresql` on 2026-10-29: `18.3`, `18.4` and `18.6` with the suffix `-system-trixie`, and `19rc1` as the only Postgres 19 tag.
- `kubectl get clusters.postgresql.cnpg.io -A`: all 4 clusters use `primaryUpdateStrategy: unsupervised` and `primaryUpdateMethod: restart`.
- CNPG documentation, [PostgreSQL upgrades](https://cloudnative-pg.io/docs/1.27/postgres_upgrades): `pg_upgrade` does not transfer optimizer statistics, an ANALYZE afterwards is up to the operator, and a point-in-time recovery does not cross a major version.
