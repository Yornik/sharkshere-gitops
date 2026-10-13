# Mazda 6e bridge

The `mazda6e-bridge` Application polls the Mazda 6e cloud API and exports the state of the car to Prometheus. Grafana shows it on the "Mazda 6e" dashboard. This file says how to activate the bridge, how to check it and how to replace its credentials.

| Item | Value |
|---|---|
| Manifests | `manifests/mazda6e-bridge/` |
| Namespace | `monitoring` |
| Image | `ghcr.io/yornik/mazda6e-grafana-bridge` |
| Source | [`Yornik/mazda6e-grafana-bridge`](https://github.com/Yornik/mazda6e-grafana-bridge) |
| Secret | `mazda6e-api`, from `manifests/mazda6e-bridge/mazda6e-api-secret.enc.yaml` |
| Metrics | `:9120/metrics`, scraped every 60 s. The bridge polls Mazda every 120 s. |

The bridge only reads. It cannot lock, unlock or control the car. CI in the source repository rejects any code that calls a write endpoint.

WARNING: The Secret holds the Mazda email, the password and a verified device ID. Together they are a full login to the Mazda account. Anyone with all three can start climate control, flash the lights or change the charge limit from other software. Keep the values only in the SOPS file.

## How to activate the bridge

Do this once. The Application cannot start without the Secret.

Prerequisites:

- The release `v1.0.0` of the image exists. See [If the image does not exist](#if-the-image-does-not-exist).
- Docker and `sops` on your computer.
- The Mazda app account that has the car.

### 1. Make a device ID

1. Run this command:

   ```sh
   python3 -c 'import uuid; print(uuid.uuid4())'
   ```

2. Write down the output. This is `MAZDA_DEVICE_ID`.

CAUTION: Do not change the device ID after step 2. A new device ID needs a new email code, and the bridge stops polling until you verify it.

### 2. Verify the device ID

Mazda sends a six-digit code by email the first time a device ID logs in. Do this step on your computer.

1. Set the 3 values in your shell:

   ```sh
   export MAZDA_EMAIL='you@example.com'
   export MAZDA_PASSWORD='your-mazda-app-password'
   export MAZDA_DEVICE_ID='the-uuid-from-step-1'
   ```

2. Run the verification:

   ```sh
   docker run --rm -it \
     -e MAZDA_EMAIL -e MAZDA_PASSWORD -e MAZDA_DEVICE_ID \
     ghcr.io/yornik/mazda6e-grafana-bridge:v1.0.0 verify-device
   ```

3. Find the code in the email from Mazda.
4. Type the code at the prompt.

Expected result: `Device verified. Keep MAZDA_DEVICE_ID unchanged from now on.`

NOTE: If the output says `already verified`, the device ID is already verified. Continue with step 3.

### 3. Test the real Mazda API

This step proves that the login and the data work before the cluster depends on them.

1. Start the bridge on your computer:

   ```sh
   docker run --rm -d --name mazda6e-test -p 9120:9120 \
     -e MAZDA_EMAIL -e MAZDA_PASSWORD -e MAZDA_DEVICE_ID \
     ghcr.io/yornik/mazda6e-grafana-bridge:v1.0.0
   ```

2. Wait 10 seconds.
3. Read the log:

   ```sh
   docker logs mazda6e-test
   ```

4. Read the metrics:

   ```sh
   curl -s localhost:9120/metrics | grep -E '^mazda6e_(scrape_success|battery_soc_percent|range_km)'
   ```

5. Stop the test container:

   ```sh
   docker stop mazda6e-test
   ```

Expected result: the log shows `polled 1 of 1 vehicle(s)`. The metrics show `mazda6e_scrape_success 1.0` and the battery charge of the car.

If the result is different, see [Problems](#problems).

### 4. Encrypt the Secret

WARNING: Do not commit the plain file. The plain file holds a full login to the Mazda account. Encrypt it before `git add`.

1. Write the file `manifests/mazda6e-bridge/mazda6e-api-secret.enc.yaml`:

   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: mazda6e-api
     namespace: monitoring
   type: Opaque
   stringData:
     MAZDA_EMAIL: you@example.com
     MAZDA_PASSWORD: your-mazda-app-password
     MAZDA_DEVICE_ID: the-uuid-from-step-1
   ```

2. Encrypt the file in place:

   ```sh
   sops --encrypt --in-place manifests/mazda6e-bridge/mazda6e-api-secret.enc.yaml
   ```

3. Check that the values are encrypted:

   ```sh
   grep -c 'ENC\[' manifests/mazda6e-bridge/mazda6e-api-secret.enc.yaml
   ```

   Expected result: a number greater than 0. Each value starts with `ENC[`.

4. Clear the plain values from your shell:

   ```sh
   unset MAZDA_EMAIL MAZDA_PASSWORD MAZDA_DEVICE_ID
   ```

### 5. Deploy

1. Commit the encrypted file to the branch of the pull request that adds the bridge.
2. Push the branch.
3. Make sure that CI is green.
4. Merge the pull request.
5. Check the Application in ArgoCD. Make sure it reports Synced and Healthy.

### 6. Check the bridge in the cluster

1. Read the log of the pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring logs deploy/mazda6e-bridge
   ```

2. Open the "Mazda 6e" dashboard in Grafana.

Expected result: the log shows `polled 1 of 1 vehicle(s)`. The "Last poll" panel on the dashboard shows OK.

## Problems

| Log line | Cause | Correction |
|---|---|---|
| `this MAZDA_DEVICE_ID is not verified yet` | The device ID in the Secret is not verified. | Do [step 2](#2-verify-the-device-id) with the device ID from the Secret. Then restart the pod. |
| `login refused (code …)` | The email or the password is wrong. | Replace the Secret. See [How to replace the credentials](#how-to-replace-the-credentials). |
| `failed to list vehicles: … HTTP 5xx` | The Mazda cloud has a problem. | No action. The bridge tries again at the next poll. |
| `failed to list vehicles: … ConnectionError` | The pod cannot reach the Mazda cloud. | Check the egress of the cluster to `cma-m.iov.changanauto.com.de`. |

NOTE: After a refused login, the bridge waits 1 hour before it tries the password again. This prevents a lockout of the Mazda account. After a correction, restart the pod to try at once:

```sh
kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/mazda6e-bridge
```

## How to replace the credentials

Do this if you change the Mazda password, or if the credentials leaked.

1. If the credentials leaked, change the Mazda password in the Mazda app first.
2. If the control PIN can also have leaked, change the control PIN in the Mazda app.
3. Edit the encrypted file:

   ```sh
   sops manifests/mazda6e-bridge/mazda6e-api-secret.enc.yaml
   ```

4. Change the values.
5. Save the file. `sops` encrypts it again.
6. Open a pull request with the change.
7. Merge the pull request.
8. Restart the pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/mazda6e-bridge
   ```

NOTE: Keep the same device ID if it did not leak. Then no new email code is necessary.

## If the image does not exist

The image comes from release-please in the source repository. Release-please opens a release pull request. The merge of that pull request builds and pushes the image.

1. In the source repository, open Settings, then Actions, then General.
2. Enable "Allow GitHub Actions to create and approve pull requests".
3. Run the failed `release-please` workflow again.
4. Merge the release pull request that release-please opens.
5. Make sure that the package `mazda6e-grafana-bridge` in GHCR is public. If it is private, the cluster cannot pull the image.
