# PrivateBin taken offline for the unpatched php2shell PHP core RCE

**Date:** 2026-10-21
**Component:** `privatebin` Deployment (`secrets.yornik.eu`)
**Severity:** a public PHP service exposed to an unpatched critical RCE, taken offline on purpose

## Effect

PrivateBin is scaled to 0 replicas. `secrets.yornik.eu` returns an error from
Traefik. The service is offline on purpose.

PrivateBin is the only PHP workload in the cluster. It runs on PHP-FPM and
serves a public domain. It is exposed to the php2shell PHP core remote code
execution flaws. No patched PHP runtime is published yet.

No other workload is affected. No other PHP workload exists in `manifests/` or
`apps/values.yaml`.

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

## Prevention

Do not restore by setting `replicas` back to 1 on tag `2.1.0`. Do not revert the
scale-down commit on its own. Both restart the unpatched PHP runtime.

The Deployment sets no `imagePullPolicy`. A node can reuse a cached `2.1.0` even
if upstream re-pushes that tag. A bare revert is not a safe restore.

To restore:

1. Find which PHP branch the image runs. Run `php -v` in the container. The
   expected fixed versions are 8.5.12, 8.4.27, 8.3.36 and 8.2.35.
2. Bump `image` to a PrivateBin release built on the fixed version of that
   branch, once PHP publishes it.
3. Set `replicas` to 1 in the same change.

Renovate watches `manifests/**/*.yaml`. A new upstream tag arrives as its own
pull request. Pair the `replicas` change with that pull request.

CAUTION: Renovate opens no pull request if upstream re-pushes `2.1.0` in place.
The image has no digest pin, so a re-push is invisible. In that case, pin the
new digest (`2.1.0@sha256:...`) and set `replicas` to 1 in the same change.

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
