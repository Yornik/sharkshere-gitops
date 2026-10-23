# TrueNAS web interface on the tailnet

The `truenas-ui` Application publishes the TrueNAS web interface at `https://nas.hedgehog-wage.ts.net`. This file says how the path works, which settings on the NAS matter, how to check the path and how to repair it. The shared steps for a new proxy device are in [`tailnet-only-admin-uis.md`](tailnet-only-admin-uis.md).

| Item | Value |
|---|---|
| Address | `https://nas.hedgehog-wage.ts.net` |
| Manifests | `manifests/truenas-ui/` |
| Namespace | `truenas-ui` |
| Image | `nginx:1.31-alpine` |
| NAS | `192.168.1.42`, HTTPS port 443 |
| Public route | none |

## How it works

```text
tailnet device -> Tailscale proxy "nas" -> Service truenas-ui :443 -> relay pod :8443 -> NAS :443
```

1. The proxy device `nas` ends TLS with a certificate for the ts.net name.
2. The proxy opens TLS to the Service `truenas-ui`. It accepts any certificate.
3. The relay pod copies the bytes to `192.168.1.42:443`. It does not read them.
4. The NAS answers with its own self-signed certificate. The proxy accepts it without a check.

NOTE: The NAS is not a pod, so a Service cannot select it. ArgoCD drops an `EndpointSlice` from git, and the Tailscale operator refuses an `ExternalName` Service. The relay pod gives the operator a Service with a ClusterIP. See [`2026-10-23-argocd-drops-endpointslice-from-git.md`](../incidents/2026-10-23-argocd-drops-endpointslice-from-git.md).

## Settings on the NAS

The new hostname needs no change on the NAS. The facts below come from the TrueNAS source of the releases 24.10.2.4, 25.04.2.6, 25.10.7, 26 and 27.0.0-RC.1.

- TrueNAS does not check the `Host` header or the `Origin` header. It only copies `Host` into a redirect and into the server URL of the API docs page.
- An unknown `Host` reaches the default server block of the NAS, which serves the web interface.
- The Tailscale proxy passes `Host: nas.hedgehog-wage.ts.net` to the NAS unchanged.
- The redirect from `/` to `/ui/` copies the `Host` header of the request. The browser stays on `nas.hedgehog-wage.ts.net`.
- In the TrueNAS middleware, the word "origin" means the IP address of the client. It does not mean the `Origin` header.

What can break is the client address. The NAS sees the address of the cluster node that runs the relay pod, not the address of your device. The nodes are `192.168.1.192` to `192.168.1.195`.

NOTE: Make sure of the node addresses with `kubectl --context yornik-sharkshere get nodes -o wide`.

### Read the settings

1. Open the shell of the NAS.
2. Run this command:

   ```sh
   midclt call system.general.config
   ```

3. Read the 4 fields in the table below.

| Field | Where | Needed value | Reason |
|---|---|---|---|
| `ui_address` | System, General Settings, GUI | Contains `0.0.0.0` or `192.168.1.42` | The relay connects to `192.168.1.42`. If the interface listens on other addresses only, the relay cannot connect. |
| `ui_httpsport` | System, General Settings, GUI | `443`, or the port in `proxy_pass` in `manifests/truenas-ui/nginx.conf` | The relay connects to this port. The default is 443. |
| `ui_allowlist` | System, Advanced Settings, Allowed IP Addresses | Empty. Otherwise it holds the 4 node addresses. | A list that does not hold the node address makes the NAS refuse the websocket. The page loads, but the dashboard stays empty. The default is empty, which allows every address. |
| `ui_httpsredirect` | System, General Settings, GUI | Any value | The relay uses the HTTPS port. This setting only changes port 80. The default is off. |

CAUTION: If `ui_allowlist` is not empty, add the 4 node addresses. Then every tailnet device that reaches `nas` passes the list. The list no longer limits your clients. The tailnet is the only limit.

NOTE: When you save the list, TrueNAS restarts the web service and warns that it can lock out your own address. Save it from the LAN address `https://192.168.1.42`, not from `nas.hedgehog-wage.ts.net`.

WARNING: Do not change the HTTPS port or the interface address in the GUI settings while you use `nas.hedgehog-wage.ts.net`. The web interface then sends the browser to `nas.hedgehog-wage.ts.net` on the new port. The relay does not publish that port, so the page is lost. Change the setting from `https://192.168.1.42`. Then change `proxy_pass` in `nginx.conf`.

CAUTION: Keep the relay a plain TCP copy to the HTTPS port of the NAS. From release 25.04, TrueNAS revokes an API key that it receives over an insecure transport. A relay that ends TLS, or that connects to port 80, makes TrueNAS treat each call as insecure.

### What the NAS sees

- The audit log and the session list show a node address, not the tailnet device.
- TrueNAS allows 20 unauthenticated calls, such as the login, for each method and each client address in 60 seconds. All tailnet devices share the node address. Many failed logins from a single device can delay the login of the other devices.
- The links to the web portals of apps on the NAS name the port of the app. The relay publishes port 443 only, so those links do not work through `nas.hedgehog-wage.ts.net`. Use `https://192.168.1.42` at home.
- TrueNAS ties its auth tokens to the client address. If the relay pod moves to another node, the address changes. The web interface can then ask for a login again.

### Hostname of the NAS

The web interface has no hostname setting. The GUI form has fields for the address and the ports only. The name comes from the address bar of the browser, and TrueNAS accepts any name. So the web interface works under `nas.hedgehog-wage.ts.net` with the hostname that the NAS has now.

The hostname of the NAS is a separate setting, in System, Network, Hostname and Domain. It names the NAS to its own clients and in its metrics. No rename is needed for this change.

If you rename the NAS anyway, check these items first:

1. Open each file `manifests/democratic-csi/*.enc.yaml` with `sops -d`. Look for the old name. The repository cannot show it, because the files are encrypted.
2. Look at `manifests/truenas-monitoring/configmap-mapping.yaml`. It maps the host part of each Graphite metric name to the label `instance`. The host part is probably the hostname of the NAS, so a rename gives new series. Nothing in this repository selects on the value. A dashboard that you made in the Grafana UI can.
3. Update each DNS or DHCP entry for the old name, and each SMB or NFS client that uses it.

CAUTION: If a CSI file names the NAS by its old hostname, a rename breaks the storage mounts. A storage fault took databases offline on 2026-10-12. See [`2026-10-12-truenas-update-readonly-pv-remount.md`](../incidents/2026-10-12-truenas-update-readonly-pv-remount.md).

NOTE: Alloy sets `instance = "nas"` for the TrueNAS logs in `apps/values.yaml`. A rename does not change that label. The SMB volumes use `192.168.1.42`, so a rename does not change them.

## How to check the path

1. Check the pod:

   ```sh
   kubectl --context yornik-sharkshere -n truenas-ui get pods
   ```

   Expected result: 1 pod, `1/1 Running`.

2. Check that the Ingress has an address:

   ```sh
   kubectl --context yornik-sharkshere -n truenas-ui get ingress truenas-ui-tailnet
   ```

   Expected result: the `ADDRESS` is `nas.hedgehog-wage.ts.net`. If it is empty, the proxy device waits for a Tailnet Lock signature. See [How to activate a new proxy device](tailnet-only-admin-uis.md#how-to-activate-a-new-proxy-device).

3. On a tailnet device, check that the NAS answers under the new name:

   ```sh
   curl -sSI https://nas.hedgehog-wage.ts.net/
   ```

   Expected result: status `302` and `location: https://nas.hedgehog-wage.ts.net/ui/`. The NAS copied the new name into the redirect.

4. Open the address in a browser and log in. Expected result: the dashboard shows live graphs. The graphs need the websocket.
5. On the shell of the NAS, read the client address of the last requests:

   ```sh
   tail -n 3 /var/log/nginx/access.log
   ```

   Expected result: the first field of each line is a node address.

## How to change the NAS address

The relay holds the address of the NAS as a literal in `manifests/truenas-ui/nginx.conf`.

1. Change `proxy_pass` in `manifests/truenas-ui/nginx.conf`.
2. Find the other files that hold the old address:

   ```sh
   grep -rn 192.168.1.42 manifests/
   ```

   The SMB volumes of Jellyfin and qBittorrent use the same address.

3. Open a pull request and merge it.

The name of the generated ConfigMap holds a hash of `nginx.conf`. A change to the file changes the name, so the Deployment starts a new pod. Nothing else needs a restart.

## If the page does not load

| Symptom | Cause | Action |
|---|---|---|
| The name does not resolve | The proxy device waits for a Tailnet Lock signature | Sign it. See [How to activate a new proxy device](tailnet-only-admin-uis.md#how-to-activate-a-new-proxy-device). |
| The device is called `nas-1` | An old device still holds `nas` | Remove the old device. Rename the new one to `nas`. |
| The proxy returns a 502 error | The relay pod is down, or the NAS is off or unreachable | Read the log of the relay. Look for `connect() failed`. Check the power and the network of the NAS. |
| The page loads and the dashboard stays empty | `ui_allowlist` does not hold the node address | Add the 4 node addresses, or empty the list. |
| The login shows `Rate Limit Exceeded` | Many failed logins from the shared node address | Wait a few minutes. |
| The sign-in page reconnects about once a minute | On 24.10 and 25.04, the NAS closes a silent websocket after 60 seconds | Do nothing. The same happens at `https://192.168.1.42`. |
| The Ingress has the event `InvalidIngressBackend` | The Service `truenas-ui` has no ClusterIP | Restore `manifests/truenas-ui/service.yaml`. Do not use `ExternalName`. |
| The Application has the condition `ExcludedResourceWarning` | Someone added an `Endpoints` or an `EndpointSlice` | Remove it from `manifests/truenas-ui/`. |

To read the log of the relay:

```sh
kubectl --context yornik-sharkshere -n truenas-ui logs deploy/truenas-ui
```

## What this path gives up

- Tailnet traffic does not pass through Traefik. The shared `security-headers`, `fail2ban` and `rate-limit` middleware do not apply. The TrueNAS login is the gate.
- The proxy does not check the certificate of the NAS. A device on the home network that answers for `192.168.1.42` can read the traffic from the proxy, including the login. WireGuard encrypts the tailnet hop only.
- The path carries the web interface only. It does not carry SMB. See [SMB shares](#smb-shares).

## SMB shares

This path does not carry SMB. A Tailscale Ingress serves HTTPS on port 443 only. SMB has its own path and its own device, `nas-smb`. See [`truenas-smb.md`](truenas-smb.md).

## How to undo the change

See [Undo the TrueNAS change](tailnet-only-admin-uis.md#undo-the-truenas-change).
