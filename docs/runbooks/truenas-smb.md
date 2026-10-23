# TrueNAS SMB shares on the tailnet

The `truenas-smb` Application publishes the SMB service of the NAS at `nas-smb.hedgehog-wage.ts.net`, on TCP port 445. This file says how the path works. It also says what a person sets up, how to connect from Windows, how to check the path and how to repair it. The web interface of the NAS has its own path. See [`truenas-ui.md`](truenas-ui.md).

| Item | Value |
|---|---|
| Address | `\\nas-smb.hedgehog-wage.ts.net\<share>` |
| Manifests | `manifests/truenas-smb/` |
| Namespace | `truenas-smb` |
| Image | `nginx`, with an `alpine` tag. See `deployment.yaml`. |
| NAS | `192.168.1.42`, port 445 |
| Share | `lilnasx`. The paths of the SMB volumes in the cluster start with `//192.168.1.42/lilnasx/`. |
| Public route | none |

WARNING: This path puts the SMB login of the NAS in reach of every tailnet device that the tailnet policy allows. Allow your own devices only, as in [What a person sets up](#what-a-person-sets-up). Use a NAS account with rights to the share only.

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

The merge creates the proxy device `nas-smb`. Tailnet Lock holds it until a trusted key signs it. Until then, nothing reaches the NAS through it. The signature opens the path.

The proxy has a tag of its own, `tag:nas-smb`. The tag keeps the device out of each rule for `tag:k8s`. The jump hosts on the internet reach `gitlab-shell`, which has that tag, so a rule for them probably covers it. After the signature, the path stays closed until a rule names `tag:nas-smb`.

WARNING: Do not sign a device that has the tag `tag:k8s`. Each rule for that tag then covers the SMB login of the NAS. The first device of this Application has that tag, because the manifest set no tag when it first merged. See [Replace a proxy that has the wrong tag](#replace-a-proxy-that-has-the-wrong-tag).

CAUTION: If the tag is not in `tagOwners`, the operator cannot create a proxy with it. No device appears. Do step 1 before the merge.

In the tailnet policy. It is in the Tailscale admin console, not in this repository:

1. Add `tag:nas-smb` to `tagOwners`. Give it the same owner as `tag:k8s`.
2. Add a rule that allows `tcp:445` from your PC to `tag:nas-smb`.

For example, in the format `grants`:

```json
{
  "tagOwners": {
    "tag:nas-smb": ["tag:k8s-operator"]
  },
  "grants": [
    {
      "src": ["<your PC or your group>"],
      "dst": ["tag:nas-smb"],
      "ip": ["tcp:445"]
    }
  ]
}
```

NOTE: Copy the owner of `tag:k8s` from your policy. The owner above is the owner in the standard operator setup. If your policy uses the format `acls`, write the destination as `tag:nas-smb:445`.

After the merge:

1. In the Tailscale admin console, find the device `nas-smb`.
2. Make sure that it has the tag `tag:nas-smb`. If it has `tag:k8s`, do [Replace a proxy that has the wrong tag](#replace-a-proxy-that-has-the-wrong-tag) first.
3. Sign the device with Tailnet Lock. See [How to activate a new proxy device](tailnet-only-admin-uis.md#how-to-activate-a-new-proxy-device). The address is unreachable until you sign it.

On the NAS:

1. Make an SMB user with rights to the share only. Do not use the account of the cluster volumes.
2. If the share has a Hosts Allow list, add the 4 node addresses `192.168.1.192` to `192.168.1.195`. The NAS sees the node that runs the relay pod, not your PC.

NOTE: Make sure of the node addresses with `kubectl --context yornik-sharkshere get nodes -o wide`.

### Replace a proxy that has the wrong tag

The operator sets the tags when it creates a proxy. It does not change the tags of a proxy that exists. A proxy with the wrong tag therefore needs a new proxy and a new signature.

WARNING: The address is unreachable from step 2 until you sign the new device in step 6.

1. Make sure that `tag:nas-smb` is in `tagOwners`.
2. Remove the old `nas-smb` device in the Tailscale admin console. If you do not, the new device joins as `nas-smb-1`.
3. Delete the Service. ArgoCD creates it again, and the operator creates a new proxy:

   ```sh
   kubectl --context yornik-sharkshere -n truenas-smb delete service truenas-smb
   ```

4. Wait until the new device appears in the admin console.
5. Make sure that the new device has the tag `tag:nas-smb`.
6. Sign the new device.

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

   Expected result: 1 StatefulSet, `1/1`. The proxy has no readiness check, so `1/1` does not show that the device is signed.

3. On a device that holds a trusted Tailnet Lock key, check the signature:

   ```sh
   tailscale lock status
   ```

   Expected result: `nas-smb` is not in the list "locked out by tailnet lock".

4. On the PC, run the port check from [Connect from Windows](#connect-from-windows).
5. Open the share and read a file.

## If it does not connect

| Symptom | Cause | Action |
|---|---|---|
| No device `nas-smb` appears | The tag is not in `tagOwners`, or the operator is down | Read the condition `ProxyReady` of the Service, as shown below. Read the log of the operator in the namespace `tailscale`. |
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

To read why the operator did not create the proxy:

```sh
kubectl --context yornik-sharkshere -n truenas-smb get service truenas-smb -o jsonpath='{.status.conditions}'
```

The operator raises no event when the Tailscale API refuses the tag. It sets the condition `ProxyReady` to false instead.

## What this path gives up

- Tailnet traffic does not pass through Traefik. The login of the NAS is the only gate, with the tailnet policy in front of it.
- The NAS sees the same client address for every tailnet device: the node that runs the relay pod. Its audit log does not show which device connected.
- The relay is 1 pod. A drain of its node, a change to `nginx.conf` or a new image tag from Renovate restarts it. Windows reconnects, and a file that is open at that moment fails.
- The NAS does not ban an address or lock an account after failed logins. Stock Samba does not, and a test of 40 wrong passwords through the relay showed no lockout. This was not checked on the NAS. Use a long password. A directory account could be locked by the directory policy, and the cluster volumes would then fail. A local account cannot. Check which kind the account of the cluster volumes is.
- WireGuard encrypts the tailnet hop only. The hops through the cluster and the home network carry SMB as the client negotiates it. To require SMB encryption, map the share with `New-SmbMapping -RequirePrivacy $true`.
- The throughput through the tailnet depends on WireGuard and on the node. It was not measured.

## How to undo the change

Revert `feat(truenas): forward SMB to the NAS over the tailnet`. The revert removes the `truenas-smb` Application, its namespace and the proxy device. If the device stays in the Tailscale admin console, remove it by hand. Nothing else depends on it.
