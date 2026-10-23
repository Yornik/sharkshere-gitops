# qBittorrent resolved no host names behind gluetun

**Date:** 2026-10-23
**Component:** `qbittorrent` Deployment, gluetun sidecar
**Severity:** no downloads from magnet links, no loss of data

## Effect

qBittorrent showed 0 DHT nodes. A magnet link stayed at "Downloading metadata". The VPN worked: the exit address was a Mullvad server, and `curl https://www.google.com` returned 200 from the pod.

## Cause

The pod uses the DNS server of gluetun at `127.0.0.1`. The resolver options are `ndots:5` and the search list `jellyfin.svc.cluster.local svc.cluster.local cluster.local yornik.nl`. The node adds `yornik.nl`.

A name with fewer than 5 dots goes through the search list first. `router.bittorrent.com` becomes `router.bittorrent.com.yornik.nl`. That name does not exist. 1.1.1.1 answers NXDOMAIN (rcode 3). gluetun answers NOERROR with no records (rcode 0).

The musl resolver in the Alpine image treats NOERROR with no records as "the name exists, but has no address". It stops and does not try the name as given. So `getaddrinfo` failed for every name with fewer than 5 dots, including the DHT bootstrap servers and the trackers.

NOTE: `curl` to Google still worked. A test with `curl` alone does not show the fault.

## Correction

Set `dnsConfig.options` `ndots: "1"` on the qBittorrent pod. A name with 1 or more dots is tried as given first. A single label such as `qbittorrent` still uses the search list.

The change restarts the pod. Running torrents pause for about 1 minute while the VPN connects again.

## Prevention

- Test name resolution in a pod behind gluetun with `getaddrinfo`, not with `curl` or `nslookup`. Both of those resolve the name in a different way.
- Keep `ndots: "1"` on each pod that uses the gluetun DNS server.
- The other pods use CoreDNS, which returns NXDOMAIN. They are not affected.

## Evidence

Measured on 2026-10-23 from the qBittorrent container with a raw DNS query:

| Name | Via gluetun `127.0.0.1` | Via `1.1.1.1` |
|---|---|---|
| `router.bittorrent.com.yornik.nl` | rcode 0, 0 answers | rcode 3 |
| `doesnotexist12345.yornik.nl` | rcode 0, 0 answers | rcode 3 |

`getaddrinfo("router.bittorrent.com")` failed with `Name has no usable address`. `getaddrinfo("router.bittorrent.com.")`, with the trailing dot, returned `67.215.246.10`.
