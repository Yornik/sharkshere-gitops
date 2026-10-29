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

The clusters no longer name an image. Each names its major version, and the operator takes the image from a catalog. The CNPG project publishes and updates that catalog.

1. Add `manifests/cnpg-catalog`. It loads the ClusterImageCatalog `postgresql-system-trixie` from `cloudnative-pg/artifacts`, pinned to a commit. The catalog maps each major to 1 image, pinned by digest. On 2026-10-29, major 18 maps to 18.6.
2. Add the Application `cnpg-catalog` in `apps/values.yaml`, in sync wave -9. The operator brings the CRD in wave -10, and the clusters come after.
3. In the 4 `cluster.yaml` files, set `imageCatalogRef` with `major: 18`.
4. Remove the old `imageName` from each live Cluster, once, by hand. See the next section.
5. Extend the git-refs manager in `renovate.json5` for SHA-pinned raw.githubusercontent.com URLs to `manifests/cnpg-catalog/kustomization.yaml`. A `packageRule` limits it to 1 pull request a week, on Monday after the CNPG rebuild, with no automerge.

The merge of the correction restarts each cluster once on 18.6. CNPG updates the replicas one at a time and then restarts the primary in place (`primaryUpdateMethod: restart`). Writes stop for a few seconds on each cluster.

## Action on the cluster

The webhook wrote `imageName` into each live spec at creation. An apply does not remove a field that git never set, and CNPG rejects `imageName` next to `imageCatalogRef`. So the first ArgoCD sync of each cluster after the merge fails with `imageName and imageCatalogRef are mutually exclusive`. The running instances are not touched.

Git cannot express the removal. `imageName: null` in `cluster.yaml` does remove the field on an apply, but the schema check in CI rejects a `null` for a string field.

After the `cnpg-catalog` Application has synced, run this once for each cluster. 1 JSON patch removes `imageName` and sets `imageCatalogRef` in the same request, so the webhook never sees an empty spec and never writes a new default:

```bash
patch='[{"op":"remove","path":"/spec/imageName"},{"op":"add","path":"/spec/imageCatalogRef","value":{"apiGroup":"postgresql.cnpg.io","kind":"ClusterImageCatalog","name":"postgresql-system-trixie","major":18}}]'
kubectl --context yornik-sharkshere -n shared-pg patch cluster shared-pg --type=json -p "$patch"
kubectl --context yornik-sharkshere -n openproject patch cluster openproject-pg --type=json -p "$patch"
kubectl --context yornik-sharkshere -n gitlab patch cluster gitlab-pg --type=json -p "$patch"
kubectl --context yornik-sharkshere -n soiree patch cluster soiree-pg --type=json -p "$patch"
```

The live spec then matches git, and ArgoCD reports the cluster as synced. A new cluster with `imageCatalogRef` in git needs no such step: the webhook writes no `imageName` when a catalog is set.

## Upgrades from now on

A **minor** release or an image rebuild arrives as the weekly Renovate pull request for the catalog. A person merges it. Each cluster on that major then restarts once. A minor upgrade keeps the data files, and Postgres keeps its statistics, so it needs no ANALYZE. Read the release notes all the same: a minor release sometimes asks for a `REINDEX` of an index type.

A **major** upgrade, for example 18 to 19, is a change of `imageCatalogRef.major` in 1 `cluster.yaml`. Renovate never makes it. From CNPG 1.26 it is an offline in-place upgrade:

1. CNPG stops every instance of the cluster.
2. A Job runs `pg_upgrade` on the primary volume.
3. CNPG recreates the replicas from the new primary.

Before the change, check that the catalog holds the new major, that a recent backup exists, and that each extension in use exists for the new major. Change 1 cluster at a time.

CNPG does not run ANALYZE after it. From Postgres 18, `pg_upgrade` keeps most optimizer statistics, but not extended statistics. Run this in the primary after each upgrade:

```bash
vacuumdb --all --analyze-in-stages --missing-stats-only
```

Then take a new base backup. A point-in-time recovery cannot cross a major version, so the older backups cannot restore to a time after the upgrade.

CAUTION: the upgrade needs the same operating system in the old and the new image. Keep the `system-trixie` catalog.

## Prevention

1. Give each new CNPG `Cluster` an `imageCatalogRef`. With neither `imageName` nor `imageCatalogRef`, the webhook freezes the image at the day of creation.
2. The same holds for each operator that fills in a default at creation. A field that the API server writes and git does not name never changes, and no tool reports it.
3. The checks in [renovate-frozen-by-tag-suffix.md](2026-10-21-renovate-frozen-by-tag-suffix.md) also cover this case. Compare the running image of each workload with the newest tag upstream.

## Evidence

- `kubectl get clusters.postgresql.cnpg.io -A` on 2026-10-29: `spec.imageName` and `status.image` per cluster, as in the table above. No `cluster.yaml` in git set `imageName`.
- The log of the operator at its start on 2026-10-26: `"operatorImageName":"ghcr.io/cloudnative-pg/cloudnative-pg:1.30.1","postgresImageName":"ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie"`.
- The tag list of `ghcr.io/cloudnative-pg/postgresql` on 2026-10-29: `18.3`, `18.4` and `18.6` with the suffix `-system-trixie`, and `19rc1` as the only Postgres 19 tag.
- `kubectl get clusters.postgresql.cnpg.io -A`: all 4 clusters use `primaryUpdateStrategy: unsupervised` and `primaryUpdateMethod: restart`.
- `kubectl apply --dry-run=server` of a `cluster.yaml` with `imageCatalogRef` on 2026-10-29: `imageName and imageCatalogRef are mutually exclusive`. With `imageName: null` the dry run passed, and the result had no `imageName`.
- The `Validate Kubernetes Schemas` check (kubeconform `-strict`) on the commit with `imageName: null`: `at '/spec/imageName': got null, want string`, for all 4 clusters.
- The history of `image-catalogs/catalog-system-trixie.yaml` in `cloudnative-pg/artifacts`: a new commit about once a week, on Monday. The branch `main` gets commits almost every day.
- CNPG documentation, [Image catalog](https://cloudnative-pg.io/docs/1.30/image_catalog): a Cluster selects a catalog and a major with `imageCatalogRef`, and a change of the version in the Cluster or in the catalog starts the upgrade.
- CNPG documentation, [PostgreSQL upgrades](https://cloudnative-pg.io/docs/1.27/postgres_upgrades): `pg_upgrade` does not transfer optimizer statistics, an ANALYZE afterwards is up to the operator, and a point-in-time recovery does not cross a major version.
