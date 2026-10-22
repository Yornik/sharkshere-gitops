# PrivateBin taken offline for the unpatched php2shell PHP core RCE

**Date:** 2026-10-21
**Component:** `privatebin` Deployment (`secrets.yornik.eu`)
**Severity:** a public PHP service exposed to an unpatched critical RCE, taken offline on purpose

## Effect

PrivateBin was scaled to 0 replicas on 2026-10-21. `secrets.yornik.eu` returned
an error from Traefik. The service was offline on purpose.

PrivateBin is the only PHP workload in the cluster. It runs on PHP-FPM and
serves a public domain. It was exposed to the php2shell PHP core remote code
execution flaws, and no patched PHP runtime had shipped.

No other workload was affected. No other PHP workload exists in `manifests/` or
`apps/values.yaml`.

The fix shipped on 2026-10-21. The service was restored on 2026-10-22. See
Correction.

## Cause

The PHP security team confirmed 2 critical flaws in PHP core. The IDs are
CVE-2026-109618 and CVE-2026-109619. Each has a CVSS v4.0 rating of 9.2. The
name php2shell circulates for the pair.

The flaws are in PHP core. No fix exists in application code. The fix is a
patched PHP runtime.

The `privatebin/nginx-fpm-alpine:2.1.0` image runs PHP-FPM. The attack vector
is undisclosed. The route carries the shared `rate-limit` and `security-headers`
middleware. That middleware is not a reliable control against an undisclosed
vector.

## Correction

Scale the Deployment to 0 replicas in `manifests/privatebin/deployment.yaml`.
ArgoCD (`prune` + `selfHeal`) applies the change on merge. The PHP-FPM pod
terminates. See [pull request 542](https://github.com/Yornik/sharkshere-gitops/pull/542).

The change edits `spec.replicas` only. The `privatebin-data-ssd` PVC stays. The
namespace stays. The Service and both IngressRoutes stay. No paste data is lost.

PrivateBin rebuilt `nginx-fpm-alpine` on PHP 8.5.12 and re-pushed the `2.1.0`
tag in place on 2026-10-21. The service was restored on 2026-10-22. The restore
set `replicas` back to 1 and pinned `image` to that rebuild by digest
(`2.1.0@sha256:0f80fb24...`). See
[pull request 551](https://github.com/Yornik/sharkshere-gitops/pull/551).

## Prevention

Do not restore by setting `replicas` back to 1 on tag `2.1.0`. Do not revert the
scale-down commit on its own. Both restart the unpatched PHP runtime.

The Deployment sets no `imagePullPolicy`. A node can reuse a cached `2.1.0` even
if upstream re-pushes that tag. A bare revert is not a safe restore.

To restore:

1. Find which PHP branch the image runs. Run `php -v` in the container. The
   expected fixed versions are 8.5.12, 8.4.27, 8.3.36 and 8.2.35.
2. Open one pull request that sets `image` to a PrivateBin release built on the
   fixed version of that branch and sets `replicas` to 1.

Do not wait for a Renovate pull request to pair the `replicas` change with. A
patch or a minor bump of this image automerges on its own (`renovate.json5`). It
can merge with no pull request left open, and it lands with `replicas` still 0.
Open your own pull request with both changes.

CAUTION: Renovate opens no pull request at all if upstream re-pushes `2.1.0` in
place. The image has no digest pin, so a re-push is invisible. In that case, pin
the new digest (`2.1.0@sha256:...`) and set `replicas` to 1 in the same pull
request.

## Evidence

- Huntress rapid response, "php2shell: Leaked Critical PHP Vulnerabilities",
  2026-10-21: <https://www.huntress.com/blog/php2shell-leaked-critical-php-vulnerabilities>.
- The PHP news archive carries an advance notice of a security release on
  2026-10-21 at 14:00 UTC for 2 critical flaws rated CVSS v4.0 9.2.
- CVE-2026-109618 and CVE-2026-109619 (php2shell) are reported by watchTowr,
  Tenable, Sansec and others.
- `manifests/privatebin/deployment.yaml` pins `image:
  privatebin/nginx-fpm-alpine:2.1.0` and sets no `imagePullPolicy`.
- The advisory review on pull request 542 (checklist B) found that a bare
  restore to tag `2.1.0` brings the unpatched runtime back.
