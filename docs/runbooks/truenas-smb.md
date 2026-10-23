# TrueNAS SMB shares on the tailnet

The `truenas-smb` Application publishes the SMB service of the NAS at `nas-smb.hedgehog-wage.ts.net`, on TCP port 445. This file says how the path works. It also says what a person sets up, how to connect from Windows, how to check the path and how to repair it. The web interface of the NAS has its own path. See [`truenas-ui.md`](truenas-ui.md).

| Item | Value |
|---|---|
| Address | `\\nas-smb.hedgehog-wage.ts.net\<share>` |
| Manifests | `manifests/truenas-smb/` |
| Namespace | `truenas-smb` |
| Image | `nginx:1.31-alpine` |
| NAS | `192.168.1.42`, port 445 |
| Share | `lilnasx`. The paths of the SMB volumes in the cluster start with `//192.168.1.42/lilnasx/`. |
| Public route | none |

WARNING: This path puts the SMB login of the NAS in reach of every tailnet device that the tailnet policy allows. Limit the policy to your own devices. Use a NAS account with rights to the share only.

## How it works

```text
tailnet device -> Tailscale proxy "nas-smb" -> Service truenas-smb :445 -> relay pod :8445 -> NAS :445
```

1. The annotation `tailscale.com/expose` on the Service makes the Tailscale operator run the proxy device `nas-smb`.
2. The proxy sends each connection to the ClusterIP of the Service. It does not read the traffic.
3. The relay pod copies the bytes to `192.168.1.42:445`. It does not read them either.
4. Signing, encryption and the login run between the PC and the NAS. The path adds none of them and removes none.

NOTE: The NAS is not a pod, so a Service cannot select it. ArgoCD drops an `EndpointSlice` from git. The relay pod gives the operator a Service with a ClusterIP. See [`2026-10-23-argocd-drops-endpointslice-from-git.md`](../incidents/2026-10-23-argocd-drops-endpointslice-from-git.md).

NOTE: The device is not called `nas`. The Ingress of the web interface holds that name, and 1 proxy cannot serve an Ingress and an exposed Service.

CAUTION: The proxy sends every port of its tailnet address to the ClusterIP. The Service declares port 445 and no other port. Do not add a port to it. Do not add port 445 to the Service of the web interface.

## What a person sets up

Before the merge:

1. If a device called `nas-smb` exists in the tailnet, remove it. If you do not, the new device joins as `nas-smb-1`.

After the merge:

1. Sign the new proxy device with Tailnet Lock. See [How to activate a new proxy device](tailnet-only-admin-uis.md#how-to-activate-a-new-proxy-device). The address is unreachable until you sign it.
2. In the tailnet policy, allow `tcp:445` from your PC to the device `nas-smb`. The policy is in the Tailscale admin console, not in this repository. The proxy has the tag `tag:k8s`.

On the NAS:

1. Make an SMB user with rights to the share only. Do not use the account of the cluster volumes.
2. If the share has a Hosts Allow list, add the 4 node addresses `192.168.1.192` to `192.168.1.195`. The NAS sees the node that runs the relay pod, not your PC.

NOTE: Make sure of the node addresses with `kubectl --context yornik-sharkshere get nodes -o wide`.

## Connect from Windows

1. Make sure Tailscale runs on the PC. Make sure the option "Use Tailscale DNS settings" is on.
2. Check that the port answers:

   ```powershell
   Test-NetConnection nas-smb.hedgehog-wage.ts.net -Port 445
   ```

   Expected result: `TcpTestSucceeded : True`.

3. Map the share:

   ```powershell
   net use Z: \\nas-smb.hedgehog-wage.ts.net\lilnasx /user:<NAS user>
   ```

4. Enter the password of the NAS user.

If Windows says `The target account name is incorrect`, use the tailnet address of the proxy. Windows then uses NTLM.

```powershell
tailscale ip -4 nas-smb
net use Z: \\<tailnet address>\lilnasx /user:<NAS user>
```

NOTE: At home, use `\\192.168.1.42\lilnasx`. It skips the tailnet, the proxy and the relay.

NOTE: Windows 11 24H2 Pro, Enterprise and Education require SMB signing, and they block guest logons. Use a named NAS user. This path is not tested against the NAS.

CAUTION: Keep `192.168.1.42` in the SMB volumes of the cluster. Do not use the tailnet name there. The volumes would then depend on a pod of the same cluster.

## How to check the path

1. Check the pod:

   ```sh
   kubectl --context yornik-sharkshere -n truenas-smb get pods
   ```

   Expected result: 1 pod, `1/1 Running`.

2. Check the proxy device that the operator runs:

   ```sh
   kubectl --context yornik-sharkshere -n tailscale get statefulset -l tailscale.com/parent-resource=truenas-smb
   ```

   Expected result: 1 StatefulSet, `1/1`. If the pod does not become ready, the device waits for a Tailnet Lock signature.

3. On the PC, run the port check from [Connect from Windows](#connect-from-windows).
4. Open the share and read a file.

## If it does not connect

| Symptom | Cause | Action |
|---|---|---|
| The name does not resolve | The device waits for a Tailnet Lock signature, or the PC does not use Tailscale DNS | Sign the device. Turn on "Use Tailscale DNS settings". |
| The device is called `nas-smb-1` | An old device still holds `nas-smb` | Remove the old device. Rename the new one to `nas-smb`. |
| `TcpTestSucceeded : False` | The tailnet policy blocks `tcp:445`, or the relay pod is down | Read the policy. Check the pod. |
| The port answers, and the login fails | The NAS user, the password or a Hosts Allow list is wrong | Check the user. Add the node addresses to Hosts Allow. |
| `The target account name is incorrect` | Windows uses Kerberos for the name | Use the tailnet address of the proxy. |
| An open file fails after a pause in work | The relay pod restarted, or the connection dropped | Close the file and open it again. |

To read the log of the relay:

```sh
kubectl --context yornik-sharkshere -n truenas-smb logs deploy/truenas-smb
```

A line with `connect() failed` means that the relay cannot reach the NAS.

## What this path gives up

- Tailnet traffic does not pass through Traefik. The login of the NAS is the only gate, with the tailnet policy in front of it.
- The NAS sees the same client address for every tailnet device: the node that runs the relay pod. Its audit log does not show which device connected.
- The relay is 1 pod. A drain of its node, or a change to `nginx.conf`, restarts it. Windows reconnects, and a file that is open at that moment fails.
- The throughput through the tailnet depends on WireGuard and on the node. It was not measured.

## How to undo the change

Revert `feat(truenas): forward SMB to the NAS over the tailnet`. The revert removes the `truenas-smb` Application, its namespace and the proxy device. If the device stays in the Tailscale admin console, remove it by hand. Nothing else depends on it.
