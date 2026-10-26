# Shelly bridge

The `shelly-bridge` Application polls the Shelly Plus 1PM device that switches the electric water boiler. It exports the readings of the device to Prometheus. Grafana shows them on the "Shelly relay" dashboard. This file says what the bridge does, and how to configure, check and repair it.

| Item | Value |
|---|---|
| Manifests | `manifests/shelly-bridge/` |
| Namespace | `monitoring` |
| Image | `ghcr.io/yornik/shelly-bridge`, pinned by tag. Renovate opens the bump. A minor or a patch bump merges itself, without a review. |
| Source | [`Yornik/shelly-bridge`](https://github.com/Yornik/shelly-bridge) |
| Device | Shelly Plus 1PM, Gen2. The address is `SHELLY_URL` in `manifests/shelly-bridge/deployment.yaml`. |
| Secret | `shelly-bridge`, optional. It holds the device password. On 2026-10-25, git held no Secret `shelly-bridge` and no KSOPS generator. See [How to add the password](#how-to-add-the-password). |
| Metrics | `:9122/metrics`, scraped every 30 s. The bridge polls the device every 15 s. The scrape removes the `pod` and `instance` labels, so the series continue after a new pod starts. |
| Dashboard | "Shelly relay", UID `shelly-bridge`, from `manifests/shelly-bridge/grafana-dashboard.yaml`. |

## Documents

| Document | Read it when |
|---|---|
| [`../tech/monitoring.md`](../tech/monitoring.md) | You need the other exporters, the scrape path or the dashboards. |
| [`Yornik/shelly-bridge`](https://github.com/Yornik/shelly-bridge) | You change the bridge or its dashboard. The README lists every metric. |
| [`shelly-control.md`](shelly-control.md) | You need the service that switches the same relay by the price. |

## What the bridge does

- It reads the local RPC API of the device, with HTTP `GET` only.
- It exports the relay state, the power, the energy, the supply voltage and current, and the health of the device. All device series carry the label `device="boiler"`. The 4 health metrics of the bridge carry no `device` label.
- It keeps its own energy counter, `shelly_switch_energy_joules_total`. The counter starts at 0 when the bridge starts, and it does not go back when the device resets its own total.
- The cost panels of the dashboard multiply the energy of each 15-minute slot by `tibber_power_price{type="total"}` from `tibber-exporter`.
- It does not export the Wi-Fi name, the IP address or the location of the device. `Shelly.GetStatus` also returns the Wi-Fi name and the IP address, but the bridge leaves them out. The bridge does not call `Shelly.GetConfig`, which also holds the location.

The bridge calls 3 methods:

| Method | When |
|---|---|
| `Shelly.GetDeviceInfo` | At start, after an outage, after a device restart and every 10 minutes. It needs no password. |
| `Shelly.GetStatus` | Every poll. |
| `Switch.GetConfig` with `id=0` | Together with `Shelly.GetDeviceInfo`. |

## Read-only guarantee

The bridge only reads. It cannot switch the relay, change a setting, run a script, install firmware or restart the device. 3 layers enforce this, at tag `v1.0.0`:

1. The package holds no write code. It calls only the 3 read methods above.
2. The client refuses a method that is not in its allowlist before it sends anything. The HTTP session checks each request again as it leaves. A refused request raises `ReadOnlyViolation`, and the process stops.
3. The CI job `Read-only guard` in the source repository runs on every pull request and before every release. It fails if the allowlist changes or if write code appears.

WARNING: The bridge only reads, but the device accepts writes. With authentication off, any device on the LAN can switch the relay with 1 HTTP request. With authentication on, `SHELLY_PASSWORD` is the admin password of the device. Another program with it can switch the relay, change each setting and install firmware. Keep the password only in the SOPS file.

CAUTION: Do not make the device reachable from outside the home LAN. Firmware 1.7.x of the Plus 1PM serves HTTP only, and it has no protection against password guessing.

## Configuration

The Deployment sets these variables. Change them in `manifests/shelly-bridge/deployment.yaml`.

| Variable | Value | Note |
|---|---|---|
| `SHELLY_URL` | The address of the device | Scheme, host and port only. The bridge refuses a path or a password in it. |
| `SHELLY_DEVICE_NAME` | `boiler` | The `device` label. A new name starts new series. |
| `SHELLY_POLL_SECONDS` | `15` | The default. The bridge accepts 5 to 3600. |
| `SHELLY_TIMEOUT_SECONDS` | not set, so `5` | Must be below `SHELLY_POLL_SECONDS`. A whole poll can take 3 times this value, but not longer than 1 poll interval. |
| `LISTEN_PORT` | `9122` | If you change it, change `containerPort` in the same file. The Service and the ServiceMonitor select the port by its name `http`. |
| `SHELLY_PASSWORD` | From the optional Secret `shelly-bridge` | Not set until you add the Secret. |

CAUTION: Do not raise the scrape interval in `servicemonitor.yaml` above 30 s. The "Failed polls" panel needs at least 2 scrapes a minute.

NOTE: Both probes use `/healthz`, not `/readyz`. `/readyz` turns 503 when the device does not answer. A device outage is not a fault of the pod. With `/readyz`, ArgoCD would show the Application as not Healthy, and a rollout would wait for the device. Prometheus also scrapes a pod that is not ready, so `shelly_scrape_success 0` shows the outage with either probe.

## How to add the password

Do this procedure when you turn on authentication on the device. Put the password in git first. The bridge sends the password only when the device asks for it, so a password in the Secret has no effect while authentication is off. The readings then do not stop when you turn on authentication.

Prerequisites:

- `sops` on your computer. The age public key in `.sops.yaml` is enough to create the file. To open the file later, you need the age private key.
- Access to the device in the Shelly app or in the web interface of the device.

### 1. Make the encrypted Secret

CAUTION: Do not write the password to a plain file in the repository. Create the file with `sops`, so that only the encrypted file reaches the disk of the repository.

1. Choose a strong password for the device. Do not use it anywhere else.
2. Create the file:

   ```sh
   sops manifests/shelly-bridge/shelly-bridge-secret.enc.yaml
   ```

   `sops` opens an editor with an example.

3. Replace the example with this Secret. Put the password in place of `the-device-password`:

   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: shelly-bridge
     namespace: monitoring
   type: Opaque
   stringData:
     SHELLY_PASSWORD: the-device-password
   ```

4. Save the file.
5. Close the editor. `sops` encrypts the file. The rule in `.sops.yaml` matches the `.enc.yaml` name.
6. Check that the value is encrypted:

   ```sh
   grep -c 'SHELLY_PASSWORD: ENC\[' manifests/shelly-bridge/shelly-bridge-secret.enc.yaml
   ```

   Expected result: `1`.

### 2. Add the KSOPS generator

1. Create `manifests/shelly-bridge/secret-generator.yaml` with this content:

   ```yaml
   apiVersion: viaduct.ai/v1
   kind: ksops
   metadata:
     name: shelly-bridge-secrets
     annotations:
       config.kubernetes.io/function: |
         exec:
           path: ksops
   files:
     # The admin password of the Shelly device. To replace it, see
     # docs/runbooks/shelly-bridge.md.
     - ./shelly-bridge-secret.enc.yaml
   ```

2. Add the generator to the end of `manifests/shelly-bridge/kustomization.yaml`:

   ```yaml
   generators:
     - secret-generator.yaml
   ```

3. Remove the comment "No ksops generator yet" from `kustomization.yaml`.

NOTE: Keep `optional: true` in `deployment.yaml`. The pod then still starts if the Secret is missing, and the log shows the `HTTP 401` line.

### 3. Deploy

1. Commit the encrypted file, the generator and `kustomization.yaml`.
2. Open a pull request.
3. Make sure that CI is green.
4. Merge the pull request.
5. Make sure that the Application reports Synced and Healthy in ArgoCD.
6. Check that the Secret exists:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring get secret shelly-bridge
   ```

7. Restart the pod. The pod reads the Secret only when it starts:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/shelly-bridge
   ```

8. Wait for the new pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout status deploy/shelly-bridge
   ```

9. Read the first log line:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/shelly-bridge | head -1
   ```

   Expected result: the line ends with `with a password`.

### 4. Turn on authentication

CAUTION: `shelly-control` also calls the device, and it has no password. With authentication on, it can no longer read or switch the relay. Give it the password first, from its own SOPS Secret in the namespace `shelly-control`. See [`shelly-control.md`](shelly-control.md#problems).

CAUTION: Do not turn on authentication before step 9 of part 3 shows `with a password`. Without the password, the bridge logs `the device requires a password (HTTP 401)`, and the readings stop. They come back only after a restart with the Secret. After each 401, the bridge waits 5 minutes before it tries again.

1. Open the device in the Shelly app or in its web interface.
2. Turn on authentication. Use the password from part 1.
3. Wait 1 minute.
4. Read the log:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/shelly-bridge --since=5m
   ```

   Expected result: the log has no `HTTP 401` line.

5. Restart the pod. The bridge logs the state of authentication only when it starts:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/shelly-bridge
   ```

6. Wait for the new pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout status deploy/shelly-bridge
   ```

7. Read the authentication lines of the log:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/shelly-bridge | grep authentication
   ```

   Expected result: 1 line, which ends with `authentication on; device label 'boiler'`.

Expected result: the "Last poll" panel on the dashboard shows OK.

## How to replace the password

Do this to change the password, for example after a leak. The pod reads the password only when it starts. So put the new password in git first. Then change it on the device and restart the pod at once.

### 1. Put the new password in git

1. If the password leaked, change the password on the device now. The readings then stop until part 2 ends.
2. Edit the encrypted file:

   ```sh
   sops manifests/shelly-bridge/shelly-bridge-secret.enc.yaml
   ```

3. Change the value of `SHELLY_PASSWORD`.
4. Save the file. `sops` encrypts it again.
5. Check that the value is encrypted:

   ```sh
   grep -c 'SHELLY_PASSWORD: ENC\[' manifests/shelly-bridge/shelly-bridge-secret.enc.yaml
   ```

   Expected result: `1`.

6. Open a pull request with the change.
7. Make sure that CI is green.
8. Merge the pull request.
9. Make sure that the Application reports Synced and Healthy in ArgoCD.

### 2. Change the password on the device

CAUTION: Do these steps directly after part 1. From the change on the device to the restart, the bridge logs `the device refused the password (HTTP 401)`, and the readings stop. A pod that starts before the change on the device gets the same error.

1. If the password did not leak, change the password on the device.
2. Restart the pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/shelly-bridge
   ```

3. Wait for the new pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout status deploy/shelly-bridge
   ```

4. Wait 1 minute.
5. Read the log:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/shelly-bridge --since=5m
   ```

Expected result: the log has no `HTTP 401` line.

## How to check that the bridge works

1. Check the Application:

   ```sh
   kubectl --context yornik-sharkshere -n argocd get application shelly-bridge
   ```

   Expected result: `Synced` and `Healthy`.

2. Read the log:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/shelly-bridge
   ```

   Expected result: a line `found Plus1PM (model …, gen 2), firmware …, authentication on; device label 'boiler'`. While authentication is off, the line says `authentication off`, and a warning line follows.

   NOTE: The bridge writes this line only when the pod starts. It shows the state of authentication at that time. After you change authentication on the device, restart the pod to see the new state.

3. Open a tunnel to the bridge:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring port-forward svc/shelly-bridge 9122:9122
   ```

4. In a second shell, read the metrics:

   ```sh
   curl -s localhost:9122/metrics | grep -E '^shelly_(scrape_success|switch_power_watts)'
   ```

   Expected result: `shelly_scrape_success 1.0`, and the power of the boiler in W.

5. Check that Prometheus scrapes the target. Use the procedure in [`../tech/monitoring.md`](../tech/monitoring.md#how-to-check-that-prometheus-scrapes-a-target). The scrape pool is `serviceMonitor/monitoring/shelly-bridge/0`.
6. Open the "Shelly relay" dashboard in Grafana.

Expected result: the "Last poll" panel shows OK. The "Relay" and "Power" panels show values.

## Problems

The bridge writes 1 log line for each change, not 1 for each poll. While the device stays away, it writes 1 error line every 10 minutes.

| Log line | Cause | Correction |
|---|---|---|
| `authentication is off on the device` | Authentication was off when the pod started. The bridge works, but anyone on the LAN can switch the relay. | If authentication is still off, see [How to add the password](#how-to-add-the-password). If you turned it on after the pod started, restart the pod. The bridge writes this line only when it starts. |
| `the device requires a password (HTTP 401)` | Authentication is on, and the pod has no password. | See [How to add the password](#how-to-add-the-password). |
| `the device refused the password (HTTP 401)` | The password in the Secret differs from the password on the device. | See [How to replace the password](#how-to-replace-the-password). |
| `failed: ConnectionError`, for example `Shelly.GetStatus failed: ConnectionError` | The address is wrong, the device is off, or the pod cannot reach the LAN. | Check `SHELLY_URL`. Check that the device has power and Wi-Fi. Check that `dirigera-exporter` still reads its hub, because it uses the same path to the LAN. |
| `timed out after 5s`, or `the poll ran past its 15s limit` | Weak Wi-Fi or a busy device. | Check the "Wi-Fi signal" panel. |
| `answered HTTP 404` | The device at the address is not a Gen2 device. | Check `SHELLY_URL`. |
| `a different device answers at this address now` | Another device has the address. The energy counter starts again at 0. | Give the Shelly device a fixed address in the router. Correct `SHELLY_URL`. |
| `ReadOnlyViolation` | The bridge tried a request outside its allowlist. This is a fault in the bridge. The process stops, and the pod restarts. | Do not work around it. Report it privately in the source repository, under Security. |

| Symptom | Cause | Correction |
|---|---|---|
| The pod has the state `ImagePullBackOff`. | The tag does not exist, or the GHCR package is private. | Make sure that the package `shelly-bridge` in GHCR is public. On 2026-10-25 it was public, with an `amd64` image. |
| The pod stops at start with a line such as `SHELLY_POLL_SECONDS must be between 5 and 3600`. | A variable in the Deployment has a value that the bridge refuses. | Correct the variable. See [Configuration](#configuration). |
| The cost panels show No data. Every other panel works. | Prometheus has no `tibber_power_price{type="total"}` for the range. | Check the `tibber-exporter` Application and its log. |
| Every panel shows No data. | The data source variable does not select `Prometheus`. | Make sure that the copy keeps the change that the file header lists. |
| A day in "Energy per day" or "Cost per day" is much too high after a node drain. | 2 pods ran at the same time for 1 poll, and Prometheus scraped both. Their energy counters mixed in 1 series. See the comment in `servicemonitor.yaml`. | No correction in git. The other days are correct. |
