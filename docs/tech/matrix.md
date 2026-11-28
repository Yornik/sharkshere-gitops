# Matrix

This file describes the Matrix deployment of the cluster. It covers the homeserver, the IRC bridge, the media storage, the zone that carries them and how to operate all of it. Facts from the cluster were read on 2026-11-28.

## Documents

| Document | Read it when |
|---|---|
| [`README.md`](README.md) | You need the storage classes or the application inventory. |
| [`../runbooks/tuwunel.md`](../runbooks/tuwunel.md) | You deploy, register a user, check, restore or repair the stack. |
| [`database.md`](database.md) | You need where the shared Hetzner S3 credentials come from. |
| [`monitoring.md`](monitoring.md) | You touch Prometheus, Grafana or alerts. |

## At a glance

| Item | Value |
|---|---|
| Homeserver | Tuwunel, the official successor to conduwuit. 1 replica. |
| Zone | `finfra.party`, its own Cloudflare zone, for Matrix alone. |
| Public hosts | `finfra.party` (client API, federation, well-known) and `media.finfra.party` (IRC media links). |
| User IDs | `@user:finfra.party`. The `server_name` is the apex. IT CANNOT CHANGE after the first boot. |
| Federation | On `:443`, and not on `:8448`. The homeserver serves its own `/.well-known/matrix/server`. |
| State | RocksDB on a `truenas-ssd-iscsi` PVC, 5 Gi, `Recreate` strategy. |
| Media | `s3://tuwunel-media` in Hetzner Object Storage (`nbg1`). No local media. |
| S3 keys | The same Hetzner credentials the CNPG clusters archive WAL with. |
| Bridge | Heisenbridge, an appservice. IRC users get media links on `media.finfra.party`. |
| Backups | Nightly online RocksDB backup, 3 generations, on its own NAS volume. |
| Registration | Token-gated. The first account to register becomes the server admin. |
| Mail | None. The zone publishes a reject-all SPF and DMARC. |
| DANE | TLSA records for both hosts, published daily. DNSSEC was switched on with this deployment. |

## How the parts connect

```mermaid
flowchart TB
  Net([\"Internet\"])
  subgraph Edge[\"Hetzner Cloud (edge)\"]
    HAProxy[\"HAProxy (L4 :443)<br/>PROXY v2\"]
  end
  Mesh{{\"Tailscale mesh\"}}
  subgraph Cluster[\"Home cluster (Talos, Intel N150)\"]
    Traefik[\"Traefik<br/>TLS termination (Let's Encrypt)\"]
    subgraph Matrix[\"Namespace matrix\"]
      Tuwunel[\"Tuwunel :8008<br/>@user:finfra.party, token-gated<br/>1 replica, Recreate, x86-64-v3\"]
      Bridge[\"Heisenbridge :9898<br/>IRC bridge appservice\"]
      Reg[\"Shared Secret<br/>registration file\"]
    end
    subgraph DNSNS[\"Namespace external-dns\"]
      ExtDNS[\"external-dns<br/>dummy Service annotations\"]
      Cron[\"DNS policy CronJobs\"]
    end
  end
  ISCSI[(\"TrueNAS truenas-ssd-iscsi<br/>RWO ext4 zvol, real fsync<br/>RocksDB, not NFS\")]
  S3[(\"Hetzner Object Storage (nbg1)<br/>s3://tuwunel-media<br/>shared CNPG S3 keys\")]
  CF[\"Cloudflare DNSSEC zone<br/>finfra.party (Matrix only)\"]

  Net -->|\"HTTPS :443 (no :8448)\"| HAProxy
  HAProxy -->|\"PROXY v2\"| Mesh
  Mesh -->|\":443\"| Traefik
  Traefik -->|\"finfra.party (client, federation,<br/>/.well-known), security-headers,<br/>fail2ban, no rate-limit\"| Tuwunel
  Traefik -->|\"media.finfra.party<br/>/m, rewrite middleware\"| Bridge
  Tuwunel -->|\"appservice txns :9898\"| Bridge
  Bridge -->|\"tuwunel.matrix.svc.cluster.local:8008\"| Tuwunel
  Reg -.->|\"appservice_dir\"| Tuwunel
  Reg -.->|\"-c\"| Bridge
  Tuwunel -->|\"RocksDB\"| ISCSI
  Tuwunel -->|\"S3 media\"| S3
  ExtDNS -.->|\"DNS records\"| CF
  Cron -.->|\"CAA (LE only), reject-all SPF/DMARC,<br/>TLSA _443._tcp (apex + media)\"| CF
```

## The zone

`finfra.party` is a zone of its own in the same Cloudflare account as the other public zones. It serves nothing except this deployment, so the homeserver answers on the apex and no delegation exists.

- The apex `finfra.party` routes everything to Tuwunel: the client API, the federation API and both well-known files. Tuwunel serves `/.well-known/matrix/server` and `/.well-known/matrix/client` itself, so no second web server publishes them. Traefik cannot serve static files, which makes this the simple option.
- Federation peers default to port `:8448`. This cluster does not forward `:8448`; the well-known server file answers `{"m.server": "finfra.party:443"}` and peers follow it. Federation rides the same Traefik entrypoint as every other host.
- DNSSEC was switched on in Cloudflare on 2026-11-28. The DS record was live at the `.party` registry the same day, verified against the TLD nameservers.
- A daily CronJob publishes the TLSA record for `_443._tcp.finfra.party` and one for `_443._tcp.media.finfra.party`. See `manifests/external-dns/`.
- A weekly CronJob publishes a CAA record: only Let's Encrypt issues for the zone.
- A weekly CronJob publishes a reject-all SPF and DMARC. The zone sends no mail: the homeserver sends no password-reset or verification mail.

## The homeserver

Tuwunel keeps all local state in one RocksDB database directory.

- The database lives on a `ReadWriteOnce` PVC on `truenas-ssd-iscsi`: ext4 on a zvol of the SSD mirror, with `sync=standard`. Each commit gets a real `fsync`. RocksDB takes file locks that NFS cannot provide, so the volume is block storage by design. See [`database.md`](database.md#storage) for the NFS-lock incidents that moved the other databases to this class first.
- The Deployment uses the `Recreate` strategy. A rolling update on an RWO volume deadlocks on `FailedAttachVolume`.
- The image is pinned to the `x86-64-v3` platform digest of the `latest` index, because the nodes are Intel N150 (Twin Lake) and v3 is the highest level they run (no AVX-512). Upstream recommends v2 or better for RocksDB CRC32 performance. Renovate tracks `latest`, but a digest bump of this image does not automerge: `renovate.json5` turns automerge off, because a multi-arch bump can name the index or the baseline amd64 manifest, and a person re-pins the v3 manifest of the new latest.
- The node seccomp default blocks the three `io_uring` syscalls. Upstream documents this as harmless: the engine falls back to synchronous reads. The default profile is not relaxed.
- Registration is token-gated. The token sits in the Secret `tuwunel-app`; tell it only to people who can create an account. The first account to register joins the admin room and holds the server.
- The admin commands run from the admin room `#admins:finfra.party` with the `!admin` prefix.

## Media

No media touches the PVC.

- Tuwunel stores media through its S3 storage provider in the bucket `s3://tuwunel-media` on `nbg1.your-objectstorage.com`. The provider list holds only `media_on_s3`, so uploads bypass the volume and the RocksDB directory stays small.
- The credentials are the Secret `cnpg-s3-wal` in the namespace `matrix`: the same Hetzner S3 keys the CNPG clusters archive WAL with. One key reaches every bucket of the project. See [`database.md`](database.md#backups-and-restore) for the other copies.
- Tuwunel pings the bucket at startup. Wrong credentials stop the pod with a clear error, so a broken secret copy is loud here.
- The bucket was created on 2026-11-28, before the first sync, with the same keys.

## The bridge

Heisenbridge brings IRC to Matrix as a bouncer. It holds no database; its state lives in the rooms it creates, so a restart needs no volume.

- Tuwunel and Heisenbridge read one registration file from one Secret. The `as_token` and `hs_token` in it are the whole of the trust between the two.
- Tuwunel pushes transactions to `http://heisenbridge.matrix.svc.cluster.local:9898` over the in-cluster Service. The bridge calls back on `http://tuwunel.matrix.svc.cluster.local:8008`. Nothing between them crosses the edge.
- The control room owner is `@yorde:finfra.party`. A DM with `@heisenbridge:finfra.party` opens the bridge help.
- A Matrix user who sends a file to a bridged channel gets a link on IRC, not a DCC transfer. The bridge prints `https://media.finfra.party/m/<media_id>/<checksum>/<filename>` and streams the file from the homeserver when someone opens it.
- The short `/m/` path comes from the registration file. The Traefik middleware `media-rewrite` restores the bridge's hardcoded route shape, `/_heisenbridge/media/finfra.party/...`, before the request reaches the bridge. The two halves must change together.
- The checksum in the link is an HMAC over the media ID. It stops enumeration of other people's uploads. That part of the URL cannot be shortened.

## Backups

The database backs up nightly, online, through the engine that owns it.

- Tuwunel copies its RocksDB database with the RocksDB Backup engine: `!admin server backup-database` in the admin room, or a SIGUSR2 that runs the same command (`admin.signal_execute`). The server keeps serving while the copy runs.
- The CronJob `tuwunel-backup` sends that signal at 04:43 Europe/Amsterdam every night. It execs into the server pod with a Role that reaches nothing but `pods/exec` in this namespace.
- The copies land on the PVC `tuwunel-backup-ssd` (class `truenas-ssd`). A backup is a plain file copy, so it needs none of the locks that keep the live database on iSCSI, and the NAS carries it off the node. 3 generations stay; the engine shares unchanged files between them.
- Restore: stop the server, start it once with `--restore-backup`, and it replaces the database from the newest generation before opening it. The steps are in the runbook.
- Media needs no backup step: it lives in the S3 bucket, outside the cluster.
- The nightly ZFS snapshot of the NAS `ssd_pool` covers both volumes as a second, crash-consistent layer.

## Monitoring

Tuwunel serves no Prometheus endpoint, so there is no ServiceMonitor for it and no application metric. The stack rides on the default rules plus one of its own:

- Default rules: `KubePodCrashLooping` sees a restart loop, the deployment rules see a pod that leaves the Service, `KubePersistentVolumeFillingUp` sees a filling volume, and `KubeJobFailed` fires when the nightly backup Job fails - the same path the jellyfin-backup Job pages through.
- Own rule: `MatrixBackupCronStale` (in `manifests/monitoring/prometheusrule-matrix.yaml`) fires when the backup CronJob has not scheduled a Job for over 26 hours. That is the failure a Job-level alert cannot see: nothing ran at all. The gate is the standing 60 minutes.

## How to check

1. Check the pods:

   ```sh
   kubectl -n matrix get pods
   ```

   Expected result: `tuwunel`, `heisenbridge` ready, 1 replica each.

2. Check discovery:

   ```sh
   curl -s https://finfra.party/.well-known/matrix/server
   ```

   Expected result: `{"m.server": "finfra.party:443"}`.

3. Check federation from the outside. The Federation Tester at <https://federationtester.matrix.org> reports `finfra.party` as OK once DNS propagates.

4. Check the homeserver version:

   ```sh
   kubectl -n matrix exec deploy/tuwunel -- tuwunel --health-check
   ```

   Expected result: the health check connects and reports the version, exit code 0.
