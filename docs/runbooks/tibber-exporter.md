# Tibber exporter

The `tibber-exporter` Application reads the live power measurements and the prices of the home from the Tibber API. It exports them to Prometheus. Grafana shows them on the "Tibber" dashboard, and the cost panels of the "Shelly relay" dashboard use the price. `shelly-control` reads the prices from `/homes/<id>/prices` to switch the boiler. This file says what the 3 Tibber alerts mean and what to do when one fires.

| Item | Value |
|---|---|
| Manifests | `manifests/tibber-exporter/` |
| Namespace | `monitoring` |
| Image | `ghcr.io/yornik/tibber-exporter`, pinned by tag. `v1.2.0` runs from 2026-10-25, about 15:17 UTC ([PR 597](https://github.com/Yornik/sharkshere-gitops/pull/597)). Before that the tag was `v1.1.2`. The `v1.1.2` rows in this file describe the old behaviour, for reading older logs and alerts. |
| Source | [`Yornik/tibber-exporter`](https://github.com/Yornik/tibber-exporter), a fork of `terjesannum/tibber-exporter` with 15-minute prices. |
| Secret | `tibber-api`, from `manifests/tibber-exporter/tibber-api-secret.enc.yaml`. It holds the Tibber API token. |
| Metrics | `:8080/metrics`, scraped every 30 s. The scrape removes the `pod` and `instance` labels, so the series continue after a new pod starts. It also removes the address and the coordinates from `tibber_home_info`. |
| Alerts | 3 rules in `manifests/monitoring/prometheusrule-tibber.yaml`. |
| Rollout | `Recreate`, so that only 1 pod holds a live websocket for the token. |
| Probes | Both read `/healthz`, which answers while the HTTP listener runs and does not depend on Tibber. `v1.1.2` had no `/healthz`, so before `v1.2.0` both read `/metrics`. |
| Dashboard | "Tibber", UID `5rT8QDiVk`, from `manifests/tibber-exporter/grafana-dashboard.yaml`. The "Meter feed" strip at the top shows Live, Delayed or Stopped, and grey regions on the charts mark feed gaps. |

## Documents

| Document | Read it when |
|---|---|
| [`../tech/monitoring.md`](../tech/monitoring.md) | You need the other exporters, the scrape path or the alert path. |
| [`Yornik/tibber-exporter`](https://github.com/Yornik/tibber-exporter) | You change the exporter. The README lists every metric and every reconnect reason. |
| [`tailnet-only-admin-uis.md`](tailnet-only-admin-uis.md) | You need Grafana or Alertmanager, for example to silence an alert. |
| [`shelly-bridge.md`](shelly-bridge.md) | The cost panels of the Shelly dashboard show no data. |
| [`shelly-control.md`](shelly-control.md) | The boiler page says that it has no prices. Without the prices of today, its rules switch nothing. |

## How the live feed works

Tibber sends a measurement about every 10 seconds over a websocket. Tibber stops sending data on a websocket that is 24 hours old, and it does not close the websocket. This document calls that the 24-hour cut.

The exporter sends each live value with the time of the measurement. It stops sending the value when the measurement is older than 5 minutes. So Prometheus stores a live sample only when Tibber sends new data.

The behaviour changes with release `v1.2.0`:

| Event | `v1.1.2` | `v1.2.0` and later |
|---|---|---|
| The live feed fails. | The process exits with code 1. Kubernetes starts the container again. | The process opens a new session. Before each attempt it waits a random time between half and all of a delay. The delay starts at 5 s and doubles up to 5 minutes. |
| The 24-hour cut. | After 1 minute without data the process exits. On most days the container restarts 1 time, and the gap in the data is less than 2 minutes. | The exporter closes the session after 23 hours 55 minutes and opens a new one. The pod does not restart. |
| Tibber is down for a long time. | The pod goes into `CrashLoopBackOff`. The chart alerts `KubePodCrashLooping` and `KubePodNotReady` fire. | The pod stays Ready. `tibber_live_connected` reads 0, and `TibberLiveFeedDown` fires. |
| Feed health metrics | None. | `tibber_live_connected`, `tibber_live_last_message_timestamp_seconds` and `tibber_live_reconnects_total{reason}`. |

## Alerts

| Alert | Fires when | Release |
|---|---|---|
| `TibberLiveDataStale` | Prometheus stored no live measurement for 15 minutes. | `v1.1.2` and `v1.2.0` |
| `TibberLiveFeedDown` | `tibber_live_connected` reads 0 for 15 minutes. The exporter runs, but the feed delivers no new data. | `v1.2.0` only. Before that the series does not exist, and the rule returns nothing. |
| `TibberPriceNotUpdating` | The total price did not change for 2.5 hours. | `v1.1.2` and `v1.2.0` |

All 3 have the severity `warning`. With `v1.2.0`, a Tibber outage fires `TibberLiveDataStale` and `TibberLiveFeedDown` about 1 minute apart.

NOTE: A feed that flaps does not fire `TibberLiveDataStale` or `TibberLiveFeedDown`. Each burst of new data resets both rules. On 2026-10-25 a 2-minute burst cleared `TibberLiveDataStale` at 02:08 UTC, and the feed stopped again until 02:16 UTC. If the live panels show many short gaps, read `tibber_live_reconnects_total` as in [TibberLiveFeedDown](#tibberlivefeeddown). The exporter README gives a rule on `avg_over_time(tibber_live_connected[30m])` for this case.

### TibberLiveDataStale

The live panels of the Tibber dashboard show no data. The cause can be Tibber, the Pulse at the meter, the websocket, the pod or the scrape.

1. Get the state of the pod:

   ```sh
   kubectl --context yornik-sharkshere -n monitoring get pods -l app.kubernetes.io/name=tibber-exporter
   ```

2. Read the log in Grafana Explore. Use the data source `Loki` and this query:

   ```logql
   {namespace="monitoring", app="tibber-exporter"} |~ "Exiting|ended:|Error"
   ```

3. Compare the log lines with the [log table](#log-lines) below.
4. In Grafana Explore, use the data source `Prometheus`. Run this query:

   ```promql
   max by (__name__) ({namespace="monitoring", job="tibber-exporter", __name__=~"up|tibber_home_info|tibber_live_connected"})
   ```

5. Find the first row in the [state table](#exporter-state) that agrees with the result.
6. Do the action of that row.
7. If the cause is still not clear, open the Tibber app on a phone.
8. If the app also shows no live data, see [If Tibber is down](#if-tibber-is-down).

#### Exporter state

A dash means any value.

| `up` | `tibber_home_info` | `tibber_live_connected` | Meaning | Action |
|---|---|---|---|---|
| 0 or no result | - | - | Prometheus cannot scrape the exporter. | If the pod restarts, the log of step 2 gives the cause. Otherwise check the scrape target with the procedure in [`../tech/monitoring.md`](../tech/monitoring.md#how-to-check-that-prometheus-scrapes-a-target). The scrape pool is `serviceMonitor/monitoring/tibber-exporter/0`. |
| 1 | No result | - | The exporter has not loaded the homes. `v1.2.0` tries again and stays Ready without a restart. No other Tibber metric exists, so `TibberLiveFeedDown` cannot fire. | Find `Error getting homes` in the log of step 2. See [If Tibber is down](#if-tibber-is-down). |
| 1 | 1 | 0 | The live feed is down. `TibberLiveFeedDown` fires about 1 to 2 minutes after this alert, so it can still be pending. | Go to [TibberLiveFeedDown](#tibberlivefeeddown). |
| 1 | 1 | 1 | The feed came back in the last minute, or each new measurement is older than 5 minutes. | If the alert clears within 2 minutes, stop here. Otherwise find `Measurements too old` in the log of step 2. The line gives the time of the newest measurement. If that time is late, the fault is at Tibber or the Pulse. |
| 1 | 1 | No result | `v1.1.2` has no feed metrics. A dead feed restarts the pod. | Use the pod state of step 1 and the log of step 2. |

#### Log lines

| Log line | Release | Cause |
|---|---|---|
| `No measurements received for home … since …. Exiting...` | `v1.1.2` | No new data for 1 minute. Once a day this is the 24-hour cut. |
| `Measurements subscription for home … disconnected`, then `Exiting...` | `v1.1.2` | Tibber closed the websocket. |
| `OnError: …`, then `Exiting...` | `v1.1.2` | The websocket failed, for example with a 502 from Tibber. |
| `Error getting homes: …` | both | The Tibber API did not answer at start. `v1.1.2` exits. `v1.2.0` tries again. |
| `Live feed for home … ended: <reason>. Reconnecting in …` | `v1.2.0` | A session ended. See the reasons in [TibberLiveFeedDown](#tibberlivefeeddown). |
| `Measurements too old: …` | both | The newest measurement is older than 5 minutes. The live gauges are not exported. |

Loki does not hold the line with the token, because Alloy drops it. If you read the log with `kubectl` instead, filter it.

CAUTION: The log of `v1.1.2` holds the Tibber API token in the `connection_init` line. Do not copy the raw log into an issue or a chat. If the token leaked, make a new token on the Tibber developer site and replace the Secret.

```sh
kubectl --context yornik-sharkshere -n monitoring logs deploy/tibber-exporter --previous | grep -v -e connection_init -e token
```

### TibberLiveFeedDown

The exporter runs, but the live feed delivers no new data. The exporter tries again by itself.

1. In Grafana Explore, use the data source `Prometheus`. Count the session ends of the last hour by reason:

   ```promql
   sum by (reason) (increase(tibber_live_reconnects_total{namespace="monitoring", job="tibber-exporter"}[1h]))
   ```

2. Read the age of the live data in seconds:

   ```promql
   time() - max(tibber_live_last_message_timestamp_seconds{namespace="monitoring", job="tibber-exporter"})
   ```

3. Find the reason with the highest count in the table below.

During a long outage the exporter waits 2.5 to 5 minutes between attempts. A reason that ends the session at once, such as `dial_failed` or `graphql_error`, then grows by about 12 to 24 each hour. A `read_timeout` session first waits 1 minute for data, so that reason grows by about 10 to 17 each hour. On a normal day, expect about 1 `max_age` each 24 hours. Other reasons can show a few times a day.

| Reason | Meaning | Action |
|---|---|---|
| `max_age` | The exporter closed the session before the 24-hour cut. | None. About 1 each day is normal. |
| `server_close` | Tibber sent a close frame, for example 1001 "Server restart". | None, if the feed comes back. |
| `complete` | Tibber ended the subscription without an error. | None, if the feed comes back. |
| `graphql_error` | Tibber sent an error such as "unable to start stream", and no data came after it. | The fault is at Tibber. See [If Tibber is down](#if-tibber-is-down). |
| `dial_failed` | The connect, the TLS handshake or the websocket handshake failed. | If other pods reach the internet, the fault is at Tibber. Otherwise check DNS and the uplink. |
| `connection_lost` | The connection ended with EOF or a reset. | If it repeats, check the uplink of the cluster. |
| `read_timeout` | No new measurement for 1 minute, the value of `--live-feed-timeout`. | If it repeats while the Tibber app also shows no live data, check the Pulse at the meter. |

### TibberPriceNotUpdating

The exporter keeps the old price when the price query fails. The Tibber dashboard and the cost panels of the Shelly dashboard can then use an old price.

1. Compare the price on the Tibber dashboard with the price in the Tibber app.
2. If the app shows the same price for the same hours, stop here. A sunny day can keep the price flat for hours. The alert clears at the next change.
3. In Grafana Explore, use the data source `Loki`. Search the log for price errors:

   ```logql
   {namespace="monitoring", app="tibber-exporter"} |~ "(?i)price"
   ```

4. If the log shows errors from the Tibber API, see [If Tibber is down](#if-tibber-is-down). The exporter asks for prices every minute.
5. If the Tibber API works and the price stays old, restart the pod.

   NOTE: The rollout uses `Recreate`. The live data has a gap of about 1 minute during the restart.

   ```sh
   kubectl --context yornik-sharkshere -n monitoring rollout restart deploy/tibber-exporter
   ```

Expected result: the price on the dashboard agrees with the app within 2 minutes.

## If Tibber is down

The Tibber API can fail for minutes or for hours. On 2026-10-25 the live feed delivered data for 2 minutes only between 00:49 and 02:16 UTC. Nothing in the cluster can fix an outage at Tibber.

NOTE: With `v1.2.0`, do not restart the pod during an outage. A restart does not fix Tibber, and it starts the wait between attempts again at 5 s.

NOTE: With `v1.1.2`, the pod stays in `CrashLoopBackOff` during the outage. Kubernetes waits up to 5 minutes between restarts. The pod becomes Ready by itself.

1. Open the Tibber app on a phone.
2. If the app shows no live data, but it shows the price, check the Pulse at the meter. It needs power and Wi-Fi.
3. If the app also fails, wait. The exporter recovers by itself when Tibber answers.
4. If the outage lasts long, silence the Tibber alerts in Alertmanager for a set time. Alertmanager sends the e-mail again every 12 hours.
