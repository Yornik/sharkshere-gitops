# Tailnet-only admin interfaces

ArgoCD and Grafana are reachable on the tailnet only. This file says how to
reach them, what changed, and how to undo the change.

| Service | Address | Public route |
|---|---|---|
| ArgoCD | `argocd.hedgehog-wage.ts.net` | `/api/webhook` only |
| Grafana | `grafana.hedgehog-wage.ts.net` | none |

## How to reach them

1. Join the device to the tailnet.
2. Open the address from the table above.

NOTE: The `argocd` CLI also uses the tailnet address. Run
`argocd login argocd.hedgehog-wage.ts.net`.

## What changed

- The Tailscale operator publishes each Service on the tailnet. ArgoCD uses
  `manifests/argocd-config/service-tailnet.yaml`. Grafana uses
  `service.annotations` in `apps/values.yaml`.
- The public DNS record for `grafana.fedishark.eu` is removed.
- The public IngressRoute for Grafana is removed.
- The public IngressRoute for ArgoCD matches `/api/webhook` only.

The record for `argocd.fedishark.eu` stays. GitHub sends the push webhook to
it and cannot join the tailnet.

## Why the webhook stays public

ArgoCD syncs within seconds of a merge because GitHub calls
`https://argocd.fedishark.eu/api/webhook`. Without that route ArgoCD falls
back to polling. The cluster still converges, but it takes up to 3 minutes.

WARNING: Do not widen the public match to the host alone. The path is the
security boundary. A host-only match puts the API and the UI back on the
internet.

## What this change gives up

Tailnet traffic does not pass through Traefik. The shared `security-headers`,
`fail2ban` and `rate-limit` middleware do not apply to it. The tailnet is the
boundary instead. Traffic is encrypted by WireGuard.

The middleware still applies to the public ArgoCD webhook route.

## How to undo the change

Use this if the Tailscale operator does not publish a Service, or if you lose
access.

1. Revert the commit that made the change.
2. Push to `main`.
3. Wait for ArgoCD to sync.

ArgoCD keeps reconciling while its UI is unreachable. The UI is not needed to
apply a revert. If the webhook is also broken, ArgoCD picks the change up on
its next poll.

If ArgoCD itself is not reconciling, apply the revert by hand:

```sh
kubectl apply -k manifests/argocd-config/
```

## How to check the result

1. Confirm the tailnet address answers.

```sh
curl -sSI https://argocd.hedgehog-wage.ts.net/ | head -1
```

2. Confirm the public host serves the webhook path and nothing else.

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://argocd.fedishark.eu/
curl -sS -o /dev/null -w '%{http_code}\n' https://argocd.fedishark.eu/api/webhook
```

The first command returns 404. The second returns 400 or 405, because the
webhook rejects a request with no GitHub payload. Both results show the route
is correct.

3. Confirm Grafana no longer resolves in public DNS.

```sh
dig +short grafana.fedishark.eu
```

The command returns nothing.

## Open items

- `manifests/monitoring/middleware-fail2ban-grafana.yaml` is no longer
  referenced by any IngressRoute. It is kept so that restoring a public
  Grafana route needs one file, not two.
- The published `security.txt` still lists `grafana.fedishark.eu` as a
  Canonical URL. That URL no longer resolves. The file is PGP-signed and CI
  verifies the signature, so the entry has to be removed and the file
  re-signed by the key holder.
- GitLab is unchanged. The GitLab Runner reaches GitLab at
  `https://git.yornik.eu/`, so closing that host needs the Runner repointed
  at in-cluster Service DNS first. Do that in its own change.
