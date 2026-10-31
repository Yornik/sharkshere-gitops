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
| 2026-09-09 | [prometheus-release-label-selector.md](2026-09-09-prometheus-release-label-selector.md) | A monitor without the `release` label is invisible to Prometheus |
| 2026-09-17 | [stale-checkout-bootstrap-apply.md](2026-09-17-stale-checkout-bootstrap-apply.md) | A stale checkout rolled ArgoCD and its Redis backwards; one cache replica could not start |
| 2026-09-18 | [external-dns-annotation-prefix.md](2026-09-18-external-dns-annotation-prefix.md) | An auto-merged minor bump stopped ExternalDNS publishing anything, silently, for days |
| 2026-09-29 | [qbittorrent-middleware-order.md](2026-09-29-qbittorrent-middleware-order.md) | A failed qBittorrent login skipped fail2ban and rate-limit, and got no security headers |
| 2026-10-11 | [backup-prune-transient-delete-504.md](2026-10-11-backup-prune-transient-delete-504.md) | One object storage timeout made a week of alerts for a problem that corrected itself |
| 2026-10-12 | [truenas-update-readonly-pv-remount.md](2026-10-12-truenas-update-readonly-pv-remount.md) | A storage update turned 6 volumes read-only; the Postgres instance that reported Ready was the one blocking repair |
| 2026-10-13 | [readonly-alert-cleared-while-volume-broken.md](2026-10-13-readonly-alert-cleared-while-volume-broken.md) | 2 more volumes turned read-only a day later, and the alert written to catch them cleared itself while they stayed broken |
| 2026-10-21 | [renovate-frozen-by-tag-suffix.md](2026-10-21-renovate-frozen-by-tag-suffix.md) | Renovate opened no bump for a pinned image for 8 months, and nothing reported the gap |
| 2026-10-21 | [gitlab-backup-object-storage-504.md](2026-10-21-gitlab-backup-object-storage-504.md) | The GitLab backup Job failed while it copied object storage buckets, so the repository dump never reached the bucket |
| 2026-10-21 | [privatebin-disabled-php2shell-rce.md](2026-10-21-privatebin-disabled-php2shell-rce.md) | PrivateBin, the only public PHP service, taken offline during the unpatched php2shell PHP core RCE |
| 2026-10-23 | [argocd-drops-endpointslice-from-git.md](2026-10-23-argocd-drops-endpointslice-from-git.md) | ArgoCD skips an `EndpointSlice` from git, so the first design for the TrueNAS web interface on the tailnet would have shown nothing |
| 2026-10-23 | [qbittorrent-dns-search-domain.md](2026-10-23-qbittorrent-dns-search-domain.md) | qBittorrent resolved no host names, so DHT had 0 nodes and magnet links never got their metadata |
| 2026-10-23 | [truenas-smb-proxy-default-tag.md](2026-10-23-truenas-smb-proxy-default-tag.md) | The SMB proxy device joined the tailnet with the shared tag `tag:k8s`, so each rule for that tag would cover the NAS login after a signature |
| 2026-10-26 | [bootstrap-bump-without-apply-note.md](2026-10-26-bootstrap-bump-without-apply-note.md) | A Redis bump to `bootstrap/` merged with the `automerge` label and no apply note, so git moved and the cluster did not |
| 2026-10-29 | [cnpg-image-frozen-at-creation.md](2026-10-29-cnpg-image-frozen-at-creation.md) | The 4 Postgres clusters stayed on the image of their creation day, 18.3 or 18.4, while 18.6 was out, and git, ArgoCD and Renovate showed nothing |
| 2026-11-01 | [democratic-csi-rolling-tag.md](2026-11-01-democratic-csi-rolling-tag.md) | Pre-incident: the storage driver ran the rolling tag `latest` with pull policy `Always`, so a moved tag would have stopped all provisioning on TrueNAS 25.10, and no bot or review could see it. Found and corrected before it failed |

## How to add an incident

1. Copy the structure of an existing file.
2. Name the file `YYYY-MM-DD-<short-name>.md`. If the date is not known, omit the date prefix.
3. Add one row to the table above.
4. Put the correction in the manifest as a comment. Point the comment to this directory.
