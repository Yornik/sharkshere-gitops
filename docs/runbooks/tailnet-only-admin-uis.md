# Tailnet-only admin interfaces

ArgoCD and Grafana are reachable on the tailnet only, over HTTPS. This file
says how to reach them, how to activate a new proxy device, what changed, and
how to undo the change.

| Service | Address | Public route |
|---|---|---|
| ArgoCD | `https://argocd.hedgehog-wage.ts.net` | `/api/webhook` only |
| Grafana | `https://grafana.hedgehog-wage.ts.net` | none |

## How to reach them

1. Join the device to the tailnet.
2. Open the address from the table above.

NOTE: Use the full name. An `http://` address redirects to HTTPS on the same
name. A short name such as `grafana` redirects to `https://grafana/`. The
proxy sends no certificate for that name. The browser shows a TLS protocol
error, such as `ERR_SSL_PROTOCOL_ERROR`, not a certificate warning.

The `argocd` CLI also uses the tailnet address:

```sh
argocd login argocd.hedgehog-wage.ts.net
```

If the login fails, run this command:

```sh
argocd login argocd.hedgehog-wage.ts.net --grpc-web
```

## How to activate a new proxy device

Each address is a proxy device that the Tailscale operator runs. Each new or
replaced Ingress gets a new device from the operator. Tailnet Lock blocks a
new device until a trusted key signs it.

### Before you merge a change that replaces a proxy

These steps stop the new device from joining with a suffix such as
`grafana-1`. The operator deletes the old device only after the old proxy
stops. The new device can join first, while the old one still holds the name.

WARNING: The address is unreachable from the moment you remove the old device
until you sign the new one. The old proxy cannot join the tailnet again. If
the merge is delayed, the outage is longer.

1. In the Tailscale admin console, find the old `grafana` or `argocd` device.
2. Remove that device.
3. Merge the change.

### After the merge

WARNING: The address is unreachable until you sign the new device. ArgoCD
keeps syncing in the meantime, so a merge on GitHub still reaches the cluster.

1. Open a terminal on a device that holds a trusted Tailnet Lock key.
2. List the blocked devices:

   ```sh
   tailscale lock status
   ```

3. Find the `grafana` or `argocd` line under "locked out by tailnet lock".
4. Sign that device with its node key:

   ```sh
   tailscale lock sign nodekey:<key>
   ```

5. Check the device name:

   ```sh
   tailscale status | grep -E 'grafana|argocd'
   ```

Expected result: the names are `grafana` and `argocd`, without a suffix.

If a name has a suffix such as `grafana-1`, the old device still held the
name when the new one joined.

1. If the old device is still listed in the Tailscale admin console, remove it.
2. Rename the new device in the admin console to the name without the suffix.

The proxy follows the new name and gets a certificate for it.

## What changed

- The Tailscale operator publishes each UI through a Tailscale Ingress:
  `manifests/argocd-config/ingress-tailnet.yaml` and
  `manifests/monitoring/ingress-grafana-tailnet.yaml`. The proxy ends TLS with
  a certificate for the ts.net name and redirects port 80 to HTTPS.
- Until 2026-10-13 the operator published each Service directly. That proxy
  forwarded port 80 only, so a browser that tried HTTPS first timed out.
  Grafana's Service keeps `tailscale.com/expose: "false"` in
  `apps/values.yaml`, so the old proxy does not come back.
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

The change has 2 commits. Revert them in this order. A revert of the second
commit before the first one conflicts.

| Order | Commit | What its revert does |
|---|---|---|
| 1 | `feat(security): serve the tailnet admin UIs over HTTPS` | Returns to the HTTP-only Service proxies on the tailnet. |
| 2 | `feat(security): move the ArgoCD UI and Grafana to the tailnet` | Restores the public IngressRoutes and the `grafana.fedishark.eu` record. |

ArgoCD keeps reconciling while its UI is unreachable. The UI is not needed to
apply a revert. If the webhook is also broken, ArgoCD picks the change up on
its next poll.

### Reach a UI without the tailnet

Use this to get in at once, before or instead of a revert.

1. Forward a local port to the UI:

   ```sh
   kubectl --context yornik-sharkshere -n argocd port-forward svc/argocd-server 8080:80
   kubectl --context yornik-sharkshere -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
   ```

2. Open `http://localhost:8080` for ArgoCD or `http://localhost:3000` for
   Grafana.

### If a Tailscale Ingress does not publish its address

Use this if the fault is in the Ingress, for example when HTTPS is not
enabled for the tailnet.

NOTE: The revert makes new proxy devices. Sign them as in
[How to activate a new proxy device](#how-to-activate-a-new-proxy-device).

1. Revert commit 1.
2. Open a pull request with the revert.
3. Merge the pull request.
4. Wait for ArgoCD to sync.

### If the tailnet itself fails

Use this if the Tailscale operator, the tailnet or the Tailnet Lock key is the
fault. The public routes do not need the tailnet.

CAUTION: Put both reverts in 1 pull request. If ArgoCD syncs revert 1 alone,
the Grafana Service gets `tailscale.com/expose: "true"`. Server-side apply can
keep that value after revert 2, and an HTTP-only proxy device stays.

1. Revert commit 1.
2. Revert commit 2.
3. Open 1 pull request with both reverts.
4. Merge the pull request.
5. Wait for ArgoCD to sync.

### If ArgoCD itself is not reconciling

Apply the reverted ArgoCD manifests by hand. `kubectl apply` does not delete
objects, and the tailnet Ingress keeps the name `argocd` while it exists.

NOTE: The delete in step 1 waits until the operator removes the device. If the
operator is down, the delete does not finish. Remove the device in the
Tailscale admin console instead.

NOTE: This path covers ArgoCD only. The Grafana settings are in the
kube-prometheus-stack Helm values, and only ArgoCD applies them.

1. Delete the tailnet Ingress:

   ```sh
   kubectl --context yornik-sharkshere -n argocd delete ingress argocd-server-tailnet
   ```

2. Apply the reverted manifests:

   ```sh
   kubectl --context yornik-sharkshere apply -k manifests/argocd-config/
   ```

## How to check the result

Run the first 2 checks on a device that uses MagicDNS.

1. Confirm the tailnet addresses answer over HTTPS.

```sh
curl -sSI https://argocd.hedgehog-wage.ts.net/ | head -1
curl -sSI https://grafana.hedgehog-wage.ts.net/login | head -1
```

Both commands return `200`. The first request after a new device can take
some seconds, because the proxy gets its certificate then.

2. Confirm that HTTP redirects to HTTPS.

```sh
curl -sSI http://grafana.hedgehog-wage.ts.net/ | head -1
```

The command returns `301`.

3. Confirm the public host serves the webhook path and nothing else.

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://argocd.fedishark.eu/
curl -sS -o /dev/null -w '%{http_code}\n' https://argocd.fedishark.eu/api/webhook
```

The first command returns 404. The second returns 400 or 405, because the
webhook rejects a request with no GitHub payload. Both results show the route
is correct.

4. Confirm Grafana no longer resolves in public DNS.

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
- `url` in `bootstrap/argocd/argocd-cm-patch.yaml` is still
  `https://argocd.fedishark.eu`. ArgoCD uses it for links and SSO callbacks,
  not for a local login. A change needs the manual bootstrap apply.
- GitLab is unchanged. The GitLab Runner reaches GitLab at
  `https://git.yornik.eu/`, so closing that host needs the Runner repointed
  at in-cluster Service DNS first. Do that in its own change.
