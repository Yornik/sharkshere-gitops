# ExternalDNS stopped publishing after the v0.22.0 bump

**Date:** 2026-09-18
**Component:** `external-dns` Application, every Service carrying DNS annotations
**Severity:** full loss of DNS automation, no user-facing effect

## Effect

ExternalDNS published nothing from the moment the v0.22.0 bump merged until this
was corrected. No new hostname could be created and no existing record could be
updated, for any application in the cluster.

Nothing broke visibly. Every record already in Cloudflare continued to resolve,
so every site stayed up and the loss was invisible until somebody added a
hostname and it never appeared.

## Cause

ExternalDNS v0.22.0 changed the default annotation prefix from
`external-dns.alpha.kubernetes.io/` to `external-dns.kubernetes.io/`, **with no
fallback**. All 63 annotations in this repository used the alpha prefix, so
ExternalDNS recognised none of them and generated no endpoints from any source.

Renovate opened and auto-merged the bump as an ordinary docker minor
(`chore(deps): update registry.k8s.io/external-dns/external-dns docker tag to
v0.22.0`, #440). The upstream release notes carry the change under "action
required" with the warning that it *"can delete all your DNS records"*.

## Why it was not noticed

Every signal that normally catches a broken controller said the opposite:

- no errors logged, and `external_dns_source_errors_total` stayed at 0
- the pod was healthy and had restarted cleanly
- ArgoCD reported the Application `Synced / Healthy`
- every existing record was still present and still correct
- each reconcile logged `All records are already up to date`

That last line was true in the only sense ExternalDNS could still measure: it
had no desired state to compare against, because it could no longer read the
annotations that produce one.

The single contradicting signal is on the metrics port:

```
external_dns_source_endpoints_total     0     # nothing it is meant to manage
external_dns_registry_endpoints_total   32    # everything it made previously
```

A controller that can see what it created before and nothing it is supposed to
manage now is the shape of this failure.

## Why nothing was lost

`--policy=upsert-only`. ExternalDNS cannot delete records under that policy, so
the 32 existing entries were never at risk. Upstream's warning is literal for a
deployment configured to sync: the desired state was empty, and a syncing
deployment reconciles an empty desired state by removing everything.

## Correction

Migrated all 63 annotations to `external-dns.kubernetes.io/` — 11 files, a pure
rename. The alternative, `--annotation-prefix=external-dns.alpha.kubernetes.io/`,
restores the old behaviour in one line but leaves a flag to be remembered at
every future upgrade, so the repository moved to the supported default instead.

Existing records were not disturbed by the migration. The TXT registry keys
ownership on the resource — `external-dns/resource=service/vikunja/vikunja` —
not on the annotation prefix, so each record stayed owned and was left in place
rather than recreated.

## Prevention

- `--policy=upsert-only` is doing more work than it appears to. It converted a
  potential deletion of every record into a silent stall. Keep it.
- Renovate auto-merges docker minor bumps here. A container image's minor
  version is not a promise of compatibility, and this release used one to ship a
  documented breaking change. Worth deciding deliberately which images may merge
  unattended.
- `external_dns_source_endpoints_total == 0` is the alert that would have caught
  this on the day. There is no legitimate steady state for it while any
  annotated Service exists.

## Evidence

- Upstream release notes for v0.22.0, change #6424.
- `manifests/external-dns/deployment.yaml` sets no `--annotation-prefix`, so the
  default applies.
- The running pod logged `AnnotationPrefix:external-dns.kubernetes.io/` while
  every manifest used the alpha form.
