# Shelly control

The `shelly-control` Application switches the Shelly Plus 1PM relay of the electric water boiler by the Tibber electricity price. It decides every quarter hour with rules that a person sets on its web page. It replaces a cron job on a Raspberry Pi, which the owner removed on 2026-10-26. This file says how to deploy it, how to move the switching from the Pi to it, how to go back, and what to watch.

| Item | Value |
|---|---|
| Address | `https://boiler.hedgehog-wage.ts.net`, on the tailnet only. No login. |
| Tailnet device | `boiler`, with the tag `tag:boiler`. The grant for that tag in the tailnet policy decides who reaches the page. |
| Manifests | `manifests/shelly-control/` |
| Namespace | `shelly-control`, with Pod Security level `restricted`. The dashboard ConfigMap is in `monitoring`. |
| Image | `ghcr.io/yornik/shelly-control`, pinned by tag. Renovate opens the bump. A person merges each bump, also a patch. See `renovate.json5`. |
| Source | [`Yornik/Shelly-control`](https://github.com/Yornik/Shelly-control). Facts in this file hold for tag `v1.0.0`. |
| Device | The relay that `shelly-bridge` reads. The address is `SHELLY_URL` in `manifests/shelly-control/deployment.yaml`. Authentication is off on the device. |
| Prices | `GET /homes/<id>/prices` on `tibber-exporter` in `monitoring`, port 8080. The service has no Tibber token. |
| Master switch | `ALLOW_SWITCHING` in `deployment.yaml`, set to `"true"`. The mode on the page decides when the rules switch. Set `"false"` to stop all switch commands (`Switch.Set`), an override included. The service always reads the relay's status. |
| Secret | none. The device has no password, and the home id is not a secret: Prometheus holds it as a label. |
| State | The PVC `shelly-control-state-ssd`, 1Gi, `truenas-ssd`, at `/data`. ArgoCD does not prune it. |
| Metrics | `:9123/metrics`, scraped every 30 s. The scrape removes the `pod` and `instance` labels. |
| Dashboard | "Shelly control", UID `shelly-control`, from `manifests/shelly-control/grafana-dashboard.yaml`. |
| Alerts | Only the chart alerts for pods, Deployments and scrape targets, such as `KubePodCrashLooping`, `KubePodNotReady`, `KubeDeploymentReplicasMismatch` and `TargetDown`. No rule reads a `shelly_control_` metric. See gap G17 in [`../tech/monitoring.md`](../tech/monitoring.md#gaps). |

## Documents

| Document | Read it when |
|---|---|
| [`tailnet-only-admin-uis.md`](tailnet-only-admin-uis.md) | You sign the new proxy device, or the address does not answer. |
| [`truenas-smb.md`](truenas-smb.md) | You set up the tailnet policy for a proxy with a tag of its own. That runbook has the same steps for `tag:nas-smb`. |
| [`../incidents/2026-10-23-truenas-smb-proxy-default-tag.md`](../incidents/2026-10-23-truenas-smb-proxy-default-tag.md) | You need the reason for the tag `tag:boiler`. |
| [`truenas-ui.md`](truenas-ui.md) | The page answers 400. It shows that the Tailscale proxy keeps the `Host` of the browser. |
| [`shelly-bridge.md`](shelly-bridge.md) | You need the readings of the relay, or you turn on authentication on the device. |
| [`tibber-exporter.md`](tibber-exporter.md) | The page says that it has no prices. |
| [`../tech/monitoring.md`](../tech/monitoring.md) | You need the scrape path, the dashboards or the gaps. |
| [`Yornik/Shelly-control`](https://github.com/Yornik/Shelly-control) | You change the service or its dashboard. The README lists the rules, every setting, every metric and every log event. |
| [`../styleguide.md`](../styleguide.md) | You edit this file. |

WARNING: The page has no login. Each tailnet device that the tailnet policy lets reach `tag:boiler` can change the rules and switch the boiler. The 2 jump hosts on the internet are tailnet devices too. A rule for `tag:k8s` lets them reach other proxies, so the boiler proxy has a tag of its own. Flannel does not enforce NetworkPolicy, so each pod in the cluster can also call the service. Do not give the page a public route.

## What the service does

- It reads the relay with `Switch.GetStatus` and switches it with `Switch.Set`. It can call no other write method. CI in the source repository enforces this.
- Every quarter hour, 5 s after the start, the first rule that applies decides. The rules in order: an override, no usable price, a negative price, the morning top-up, under the switch-on line, over the switch-off line. Between the 2 lines, the relay keeps its state.
- Each line is a factor times the average price of the day. The defaults are 1.05 to switch on and 1.25 to switch off.
- In shadow mode, the rules switch nothing. The service decides and logs. An override still switches while `ALLOW_SWITCHING` is `"true"`. Live mode needs `ALLOW_SWITCHING="true"` and a confirmation on the page.
- Without a usable price for the quarter, the rules switch nothing. The page says why.
- It keeps the last good prices on the volume. It decides on through an outage of the exporter while the prices cover today.

| Setting | Where | Value at the first deploy |
|---|---|---|
| `ALLOW_SWITCHING` | `deployment.yaml` | `"true"`. In the mode Shadow the rules switch nothing, but an override switches. |
| Mode | The page, stored in `state.json` | Shadow. `DEFAULT_MODE` is not set. |
| Factors, morning window | The page, stored in `state.json` | The defaults of `v1.0.0`. |

CAUTION: Do not set `DEFAULT_MODE=live` in the Deployment. It starts the service in live mode without the confirmation on the page.

## How to deploy the first time

### Before the merge

The Ingress makes a new proxy device with the name `boiler` and the tag `tag:boiler`. The tag keeps the device out of each rule for `tag:k8s`. See [`../incidents/2026-10-23-truenas-smb-proxy-default-tag.md`](../incidents/2026-10-23-truenas-smb-proxy-default-tag.md).

CAUTION: If `tag:boiler` is not in `tagOwners`, the operator cannot create the proxy. No device appears. Do step 1 of [1. The tailnet policy](#1-the-tailnet-policy) before the merge.

#### 1. The tailnet policy

The policy is in the Tailscale admin console, not in this repository.

1. Add `tag:boiler` to `tagOwners`. Give it the same owner as `tag:k8s`.
2. Find each rule whose destination is `*` or all tagged devices. Narrow it. A rule like that also covers `tag:boiler`. The default policy of a tailnet is such a rule.
3. Add a grant from your own devices or your group to `tag:boiler`. Allow `tcp:443` and `tcp:80`. Port 80 only redirects to HTTPS.

After these steps, only your own devices reach the page, unless another rule matches.

For example, in the format `grants`:

```json
{
  "tagOwners": {
    "tag:boiler": ["tag:k8s-operator"]
  },
  "grants": [
    {
      "src": ["<your devices or your group>"],
      "dst": ["tag:boiler"],
      "ip": ["tcp:443", "tcp:80"]
    }
  ]
}
```

NOTE: Copy the owner of `tag:k8s` from your policy. The owner above is the owner in the standard operator setup. If your policy uses the format `acls`, write the destination as `tag:boiler:443,80`.

#### 2. The device name and the Pi

A new device joins as `boiler-1` if a device named `boiler` already exists.

1. In the Tailscale admin console, search for a device named `boiler`.
2. If a device named `boiler` exists, remove it.
3. Leave the cron job on the Pi off. The owner removed it on 2026-10-26. 2 controllers of 1 relay work against each other.

### After the merge

WARNING: Do not sign a device that has the tag `tag:k8s`. Each rule for that tag then covers the boiler page, and a jump host on the internet can reach it.

1. Check the Application:

   ```sh
   kubectl --context yornik-sharkshere -n argocd get application shelly-control
   ```

   Expected result: `Synced` and `Healthy`.

2. Check the volume:

   ```sh
   kubectl --context yornik-sharkshere -n shelly-control get pvc shelly-control-state-ssd
   ```

   Expected result: `Bound`.

3. Read the start of the log:

   ```sh
   kubectl --context yornik-sharkshere -n shelly-control logs deploy/shelly-control | head -8
   ```

   Expected result: a `start` line with `"switching_allowed": true`, a `device_found` line and a `device_auth_off` warning. The warning is expected, because authentication is off on the device.

4. In the Tailscale admin console, find the device `boiler`.
5. Make sure that it has the tag `tag:boiler`. If it has `tag:k8s`, do [Replace a proxy that has the wrong tag](#replace-a-proxy-that-has-the-wrong-tag) first.
6. Sign the device. Do the steps in [After the merge](tailnet-only-admin-uis.md#after-the-merge) of `tailnet-only-admin-uis.md`. The device name is `boiler`.
7. Open `https://boiler.hedgehog-wage.ts.net`.

Expected result: the page shows the relay, today's prices, a decision and the mode Shadow.

NOTE: The first request after a new device can take some seconds, because the proxy gets its certificate then.

### Replace a proxy that has the wrong tag

The operator sets the tags when it creates a proxy. It does not change the tags of a proxy that exists. A proxy with the wrong tag therefore needs a new proxy and a new signature.

NOTE: The page is unreachable from step 3 until you sign the new device in step 6. The service goes on deciding without the page.

1. Make sure that `tag:boiler` is in `tagOwners`.
2. Make sure that `ingress-tailnet.yaml` holds the annotation `tailscale.com/tags: "tag:boiler"`.
3. Remove the old `boiler` device in the Tailscale admin console. If you do not, the new device joins as `boiler-1`.
4. Delete the Ingress. ArgoCD creates it again, and the operator creates a new proxy:

   ```sh
   kubectl --context yornik-sharkshere -n shelly-control delete ingress shelly-control-tailnet
   ```

5. Wait until the new device appears in the admin console. Make sure that it has the tag `tag:boiler`.
6. Sign the new device.

### If the page answers 400

The service answers only to the hosts in `ALLOWED_HOSTS`. The Tailscale proxy passes the `Host` of the browser to the service unchanged. The NAS path relies on the same behavior. See [`truenas-ui.md`](truenas-ui.md#settings-on-the-nas). So `boiler.hedgehog-wage.ts.net` matches. If the page still answers 400, do these steps:

1. Read the refused hosts:

   ```sh
   kubectl --context yornik-sharkshere -n shelly-control logs deploy/shelly-control | grep host_refused
   ```

2. Add the value of `host` to `ALLOWED_HOSTS` in `deployment.yaml`. Separate the names with a comma.
3. Open a pull request with the change.
4. Merge the pull request.

### How to check the metrics and the dashboard

1. Check that Prometheus scrapes the target. Use the procedure in [`../tech/monitoring.md`](../tech/monitoring.md#how-to-check-that-prometheus-scrapes-a-target). The scrape pool is `serviceMonitor/shelly-control/shelly-control/0`.
2. Open the "Shelly control" dashboard in Grafana.

Expected result: the Mode panel shows Shadow, and the Prices panel shows Usable.

## How to move the switching from the Pi

The owner removed the cron job on the Pi on 2026-10-26, before the first deploy. The shadow phase was skipped. Until someone chooses Live on the page, nothing switches the boiler. The relay keeps its state, and the boiler thermostat still protects the boiler.

WARNING: 2 controllers of 1 relay work against each other. If the cron job on the Pi comes back, choose Shadow on the page first.

NOTE: The live cron script on the Pi, `boiler2.sh` (read on 2026-10-25), switches on below 1.05 times the day's average and off above 1.25 times. Its morning rule applies only in the 05:00 quarter, with the 1.25 line. These are the defaults of `v1.0.0`. The source repository replays 5 days of prices against the switches of the Pi, and these factors reproduce them.

### 1. Check the tailnet policy

1. Read the tailnet policy in the Tailscale admin console.
2. Make sure that no rule with a jump host as source, or with a wildcard destination, covers `tag:boiler`.

### 2. Go live

1. Open the page.
2. Check that the factors are 1.05 and 1.25, and that the morning window is the 05:00 quarter.
3. Choose Live.
4. Tick the confirmation.
5. Save.

Expected result: the page shows the mode Live. `shelly_control_live` and `shelly_control_switching_allowed` read 1.

### 3. Compare the first decisions

NOTE: The Decisions list on the page shows each quarter. In Loki, the field `outcome` of a quarter is `switched`, `unchanged`, `held_back` or `failed`.

1. In Grafana Explore, use the data source `Loki`. Read the decisions:

   ```logql
   {namespace="shelly-control", app="shelly-control"} | json | event="evaluation"
   ```

2. Compare the decisions with the switches of the Pi in the days before. The "Rules want, relay is" panel shows `shelly_control_target_on` and `shelly_switch_output` of `shelly-bridge`.

### 4. Watch the next switches

Watch at least 1 switch on and 1 switch off.

| Metric or field | Expected |
|---|---|
| `shelly_control_switch_commands_total` | Grows by 1 for each switch. |
| `shelly_control_switch_failures_total` | Stays 0. |
| `shelly_control_relay_on` | Follows `shelly_control_target_on` within 1 minute. |
| The Decisions list on the page | "Switched on" or "Switched off" for each switch. Read the reason of each "Failed" or "Held back". |

## How to go back to the Pi

Use this if the service switches wrong, or if a switch fails. The page stops the switching at once. `ALLOW_SWITCHING="false"` in git keeps it stopped, an override included.

CAUTION: Stop the switching of the service first. Then start the cron job on the Pi. 2 controllers of 1 relay work against each other.

NOTE: In shadow mode, an override still switches while `ALLOW_SWITCHING` is `"true"`. When an override ends in shadow mode, nothing switches the relay back. The cron job or live mode switches it at the next decision.

CAUTION: `ALLOW_SWITCHING="false"` does not change the saved mode. A mode Live in `state.json` stays Live. If a later change sets `ALLOW_SWITCHING` to `"true"` again, the rules can switch the relay at once. The page asks for no confirmation then. A revert of the pull request is such a change.

NOTE: If the page does not answer, for example because the tailnet is down, start at step 4. Do steps 1 to 3 and step 8 as soon as the page answers.

1. On the page, choose Shadow.
2. Save.
3. If the page shows an override, choose End override now.
4. In `manifests/shelly-control/deployment.yaml`, set `ALLOW_SWITCHING` to `"false"`.
5. Open a pull request with the change.
6. Merge the pull request. ArgoCD replaces the pod.
7. Make sure that `shelly_control_switching_allowed` reads 0.
8. Make sure that `shelly_control_live` and `shelly_control_override_active` read 0.
9. On the Pi, put the cron job back.

Expected result: the Pi switches the boiler at the next quarter hour that crosses a line.

## State on the volume

The service keeps 3 JSON files in `/data`, on the PVC `shelly-control-state-ssd`:

| File | Content | If it is lost |
|---|---|---|
| `state.json` | The settings and an active override, with the last person who changed them. | The service starts with the defaults, in shadow mode. Set the factors on the page again. |
| `decisions.json` | The last 700 decisions, about 1 week. | The log on the page starts empty. Loki keeps the `evaluation` lines for 60 days. |
| `prices.json` | The last good prices. | The service reads them again from the exporter. |

- The service writes each file to a temporary file, syncs it and renames it. A crash leaves the old file or the new one.
- If `state.json` cannot be read, the service renames it to `state.json.unreadable-<time>`. It then uses the defaults in shadow mode and shows a banner.
- If a write fails, the service goes on with the state in memory. It shows a banner and counts `shelly_control_state_write_errors_total`.
- The PVC has `Prune=false`. ArgoCD does not delete it when it leaves git. `truenas-ssd` has the reclaim policy Delete, so a deleted PVC deletes the NAS dataset.

## What to watch

The chart alerts `KubePodCrashLooping`, `KubePodNotReady`, `KubeDeploymentReplicasMismatch` and `TargetDown` fire when the pod crashes, is not ready, does not roll out or stops answering the scrape. No alert covers a failed switch, a relay that the service cannot read, prices that stop or evaluations that stop. See G17. Watch these metrics on the dashboard:

| Metric | Problem when |
|---|---|
| `shelly_control_switch_failures_total` | It grows. The label `reason` says why. |
| `shelly_control_relay_read_success` | It reads 0 for more than 15 minutes. The service cannot read the relay. |
| `shelly_control_prices_usable` | It reads 0. The rules switch nothing until the prices come back. |
| `shelly_control_last_evaluation_timestamp_seconds` | It is older than 20 minutes. The service makes no decisions. |
| `shelly_control_state_saved` | It reads 0. A restart loses the changes since the last good write. |
| `shelly_control_live` and `shelly_control_switching_allowed` | After the switch-over, 1 of them reads 0. The service does not switch. |

## Problems

| Log line or banner | Cause | Correction |
|---|---|---|
| `host_refused` in the log, the page answers 400 | The Host of the request is not in `ALLOWED_HOSTS`. | See [If the page answers 400](#if-the-page-answers-400). |
| `the exporter does not serve this home` | `TIBBER_HOME_ID` differs from the `--live` argument of `tibber-exporter`. | Copy the value from `manifests/tibber-exporter/deployment.yaml`. |
| `cannot reach the exporter` | `tibber-exporter` is down, or the address is wrong. | Check the `tibber-exporter` Application. See [`tibber-exporter.md`](tibber-exporter.md). |
| `the device requires a password (HTTP 401)` | The device asks for a password, and the service has none. | Turn off authentication on the device. Or add `SHELLY_PASSWORD` from a SOPS Secret, as in [`shelly-bridge.md`](shelly-bridge.md#how-to-add-the-password), for this namespace. |
| `Changes are kept in memory only` | The volume is full or read-only. | Check the PVC and the NAS. See [`../incidents/2026-10-12-truenas-update-readonly-pv-remount.md`](../incidents/2026-10-12-truenas-update-readonly-pv-remount.md). |
| The pod has the state `ImagePullBackOff`. | The tag does not exist, or the GHCR package is private. | Make sure that the package `shelly-control` in GHCR is public. On 2026-10-26 it was public, with an `amd64` image. |
| The pod stops at start with a line about a variable. | A variable in the Deployment has a value that the service refuses. | Correct the variable. The README of the source lists the allowed values. |
| No device `boiler` appears after the merge. | `tag:boiler` is not in `tagOwners`, or the operator is down. | Do [1. The tailnet policy](#1-the-tailnet-policy). Read the log of the operator in the namespace `tailscale`. |

CAUTION: If you turn on authentication on the device, both `shelly-bridge` and `shelly-control` need the password. A Secret cannot be shared across namespaces, so each namespace needs its own SOPS file.

## How to reach the API without the tailnet

A port-forward sends the Host `localhost:9123`, which the service refuses. Send the ts.net name as the Host instead.

1. Forward a local port to the service:

   ```sh
   kubectl --context yornik-sharkshere -n shelly-control port-forward svc/shelly-control 9123:9123
   ```

2. In a second shell, read the status:

   ```sh
   curl -s -H 'Host: boiler.hedgehog-wage.ts.net' localhost:9123/api/v1/status
   ```

A browser cannot set the Host, so the page does not work through the port-forward. To stop the switching without the tailnet, set `ALLOW_SWITCHING` to `"false"` in git.
