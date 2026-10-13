# A failed qBittorrent login skipped fail2ban and rate-limit

**Date:** 2026-09-29
**Component:** `qbittorrent` IngressRoute (`qbittorrent.fedishark.eu`)
**Severity:** brute-force protection absent on one public login, no loss of service

## Effect

A failed login on `qbittorrent.fedishark.eu` did not reach the fail2ban
middleware. It did not reach the rate-limit middleware. An attacker could try
passwords against this host without a ban and without a rate limit.

The same response carried no security headers. It had no HSTS header, no
nosniff header and no frameDeny header.

Every other public host kept its protection. The fault was on this host only.

## Cause

Traefik runs the `middlewares` list in order. `basicAuth` ends the chain when it
rejects a request. Every middleware after `basicAuth` is skipped.

The list put `qbittorrent-auth` first:

```yaml
middlewares:
  - name: qbittorrent-auth   # rejects here
  - name: rate-limit         # never reached on a 401
  - name: fail2ban           # never reached on a 401
  - name: security-headers   # never reached on a 401
  - name: no-compression
```

A request with a correct password passed through the whole chain, so the host
looked correct in normal use. Only a rejected request showed the fault.

`qbittorrent` is the only application that authenticates at Traefik. The other
applications authenticate in the application itself, so no middleware ends their
chain early. This is why the fault appeared on one host.

## Why it was not noticed

The fault is only visible on a response that fails. An operator who logs in
successfully sees a correct response with all headers.

A header check on the public hosts showed the difference:
`qbittorrent.fedishark.eu` returned a 401 with no `strict-transport-security`
header, while all 15 other public hosts returned the header.

## Correction

Move `qbittorrent-auth` to the end of the list. Put `security-headers` first.

```yaml
middlewares:
  - name: security-headers
  - name: fail2ban
  - name: rate-limit
  - name: no-compression
  - name: qbittorrent-auth   # last: a 401 passes through the list above
```

This matches the order that `vikunja`, `asf` and `argocd-config` use.

## Prevention

Put an authentication middleware last in a `middlewares` list. Put
`security-headers` first.

NOTE: This rule applies to any middleware that can end a chain. `basicAuth`,
`forwardAuth` and `ipAllowList` all end the chain on a rejection.

To check a host, read the headers on a response that fails:

```sh
curl -sSI https://qbittorrent.fedishark.eu/ | grep -i strict-transport-security
```

A host that is correct returns the header on the 401.

## Evidence

Header check of all 16 public hosts on 2026-09-29. 15 hosts returned
`strict-transport-security`. `qbittorrent.fedishark.eu` returned a 401 with no
`strict-transport-security`, no `content-security-policy` and no
`x-xss-protection`.

Middleware order read from `manifests/qbittorrent/ingressroute.yaml` at commit
`50059a2`.
