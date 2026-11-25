# siemens-home-connect-exporter runbook

Read-only Prometheus exporter for Siemens and Bosch home appliances that
speak Home Connect. Source and releases:
[Siemens-home-connect-exporter](https://github.com/Yornik/Siemens-home-connect-exporter).
Image: `ghcr.io/yornik/siemens-home-connect-exporter`, signed with cosign.

The exporter runs in `monitoring`, next to the other read-only exporters.
It serves `/metrics` on port 9780 and keeps one Server-Sent Events stream
open per appliance. Home Connect counts each stream opening against a
daily budget of 1000 requests per client and user; the exporter keeps 100
in reserve and retries inside its process, so the pod stays Ready through
outages.

## Health checks

```console
kubectl -n monitoring get pods -l app.kubernetes.io/name=siemens-home-connect-exporter
kubectl -n monitoring logs deploy/siemens-home-connect-exporter --tail=50
curl -s http://siemens-home-connect-exporter.monitoring:9780/healthz
```

The log line `stream open appliance=<name>` appears once per appliance.
`homeconnect_connected` is 1 while an appliance talks to the cloud.

## Credentials

The secret `homeconnect` in `monitoring` carries `client-id`,
`client-secret` and `refresh-token`. The source file is
`manifests/siemens-home-connect-exporter/homeconnect-secret.enc.yaml`,
SOPS-encrypted to the cluster age key.

To read the current values:

```console
sops exec-file manifests/siemens-home-connect-exporter/homeconnect-secret.enc.yaml 'cat {}'
```

### Replace the refresh token

Home Connect rotates refresh tokens on every refresh and the exporter
stores the new one in memory only. When Home Connect revokes the token
(an expired grant, a removed application), the exporter logs
`invalid refresh_token` and exits. Get a new token:

1. Run the authorize flow on a machine with a browser, per the README of
   the source repository. The redirect URI is
   `http://127.0.0.1:7878/auth`. From Windows over SSH:
   `ssh -L 7878:127.0.0.1:7878 <host>` and run the flow on the host.
2. Write the new token into the secret file and re-encrypt:

```console
$EDITOR /tmp/homeconnect-secret.yaml   # stringData.refresh-token
mv /tmp/homeconnect-secret.yaml manifests/siemens-home-connect-exporter/homeconnect-secret.enc.yaml
sops encrypt -i --encrypted-regex '^(data|stringData)$' \
  manifests/siemens-home-connect-exporter/homeconnect-secret.enc.yaml
sops filestatus manifests/siemens-home-connect-exporter/homeconnect-secret.enc.yaml
```

3. Commit and merge. ArgoCD applies the new secret and recreates the pod.

The client id and secret stay valid; only the refresh token rotates.

## Alerts

`manifests/monitoring/prometheusrule-siemens-home-connect.yaml` defines:

- `HomeConnectApplianceOffline`: one appliance reported `connected == 0`
  for 1 hour. Check the appliance display and its Wi-Fi. The exporter
  keeps serving the other appliances meanwhile. No exporter action helps
  an appliance that cannot reach the cloud.
- `HomeConnectExporterNoData`: no scrape answered for 1 hour. Check the
  pod, then the logs, then Home Connect itself (status page or the app).
  A 429 in the logs means the daily budget burned: check that no second
  client (another application, a laptop run) shares the same account.

The `for` durations follow the standing 60-minute gate: transients never
page. Revisit them after 30 days of history.

## Restore

The exporter holds no state. Deleting the deployment and letting ArgoCD
recreate it restores everything. The appliance list and all metric state
come from the Home Connect API at startup.
