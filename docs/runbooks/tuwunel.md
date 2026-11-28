# Tuwunel + Heisenbridge runbook

This runbook covers the Matrix stack in the namespace `matrix`: the Tuwunel homeserver on `finfra.party`, the Heisenbridge IRC bridge and the media bucket. The stack itself: [`../tech/matrix.md`](../tech/matrix.md).

## What runs where

| Part | Where |
|---|---|
| Homeserver | `deploy/tuwunel`, port 8008, public on `https://finfra.party`. |
| Bridge | `deploy/heisenbridge`, port 9898, no public route except the media path. |
| State | PVC `tuwunel-data`, class `truenas-ssd-iscsi`, 5 Gi, `Prune=false`. |
| Media | Bucket `s3://tuwunel-media` on `nbg1.your-objectstorage.com`. |
| Secrets | `tuwunel-app` (registration token), `heisenbridge-registration` (shared registration file), `cnpg-s3-wal` (Hetzner S3 keys). |

## First deploy

The manifests reach the cluster through the ArgoCD Application `matrix`. Check the pieces before the first registration:

1. Check the pods:

   ```sh
   kubectl -n matrix get pods
   ```

   Expected result: both Deployments ready.

2. Check the DNS record:

   ```sh
   dig +short finfra.party
   ```

   Expected result: the 2 edge IPv4 addresses and 2 IPv6 addresses. If empty, read the `--domain-filter` block in `manifests/external-dns/deployment.yaml`.

3. Check discovery:

   ```sh
   curl -s https://finfra.party/.well-known/matrix/server
   ```

   Expected result: `{"m.server": "finfra.party:443"}`.

4. Wait for the Let's Encrypt certificate if this is the first boot. Traefik orders it on the first request; a 404 on the well-known file for a few minutes after the record appears is the order completing.

## Register the first account

The first account takes the server: it joins the admin room `#admins:finfra.party` and holds every `!admin` command.

1. Read the registration token:

   ```sh
   sops -d manifests/matrix/tuwunel-app.enc.yaml
   ```

   Keep the token out of logs and screenshots. It gates nothing once an account exists, but every new account needs it.

2. Open a client (for example Element) and register `@yorde:finfra.party` with the token.

3. Register friends the same way, or tell them the token. Rotate the token (see below) when someone should no longer be able to invite people.

## Use the IRC bridge

1. DM `@heisenbridge:finfra.party` from the owner account. The bridge answers with its help.

2. Create a network and connect:

   ```text
   ADDNETWORK LIBERA
   ADDSERVER LIBERA irc.libera.chat 6697 --tls
   OPEN LIBERA
   ```

3. `JOIN #channel` inside the network room.

A file sent from Matrix to a bridged channel arrives on IRC as a link on `media.finfra.party`. A file sent from IRC needs a client that can upload to the bridge; see the bridge help.

## Rotate the registration token

1. Generate a value:

   ```sh
   openssl rand -base64 24
   ```

2. Put it in the Secret:

   ```sh
   sops manifests/matrix/tuwunel-app.enc.yaml
   ```

3. Commit, merge, and wait for the sync. A reload applies the token without a restart (`registration.token` is reloadable); `!admin server reload-config` in the admin room forces it at once.

## Rotate the bridge tokens

Nothing is deployed that needs this today; skip it unless the tokens leak.

1. Generate two tokens:

   ```sh
   openssl rand -base64 96 | tr -dc 'a-zA-Z0-9' | head -c 64
   ```

2. Edit the Secret. Put the first value in `as_token`, the second in `hs_token`:

   ```sh
   sops manifests/matrix/heisenbridge-registration.enc.yaml
   ```

3. Restart both Deployments in the same change:

   ```sh
   kubectl -n matrix rollout restart deploy/tuwunel deploy/heisenbridge
   ```

## Back up and restore

The CronJob `tuwunel-backup` runs nightly at 04:43 Europe/Amsterdam. It sends SIGUSR2 to the server, which runs `server backup-database` through the RocksDB Backup engine. 3 generations stay on the PVC `tuwunel-backup-ssd`.

Run a backup by hand:

```text
!admin server backup-database
```

Verify the last run:

```sh
kubectl -n matrix get jobs --sort-by=.metadata.creationTimestamp
kubectl -n matrix logs job/tuwunel-backup-<timestamp>
```

Media needs no backup step: it lives in the S3 bucket, outside the cluster.

### Restore

1. Scale the server down:

   ```sh
   kubectl -n matrix scale deploy/tuwunel --replicas=0
   ```

2. Start a one-off pod that mounts both volumes and restores the newest generation. The pod runs under the same account as `deploy/tuwunel`; a root-owned restore would leave files the server cannot write.

   ```sh
   kubectl -n matrix run tuwunel-restore --rm -i \
     --image=ghcr.io/matrix-construct/tuwunel:latest@sha256:5e42c29ed88e77322e33d5cff7ca4b14986818da219e6eb7bc984d756396ed02 \
     --overrides '
     {
       "spec": {"containers": [{
         "name": "restore",
         "image": "ghcr.io/matrix-construct/tuwunel:latest@sha256:5e42c29ed88e77322e33d5cff7ca4b14986818da219e6eb7bc984d756396ed02",
         "args": ["--restore-backup"],
         "env": [
           {"name": "TUWUNEL_DATABASE__PATH", "value": "/var/lib/tuwunel"},
           {"name": "TUWUNEL_DATABASE__BACKUP__PATH", "value": "/var/lib/tuwunel-backups"}
         ],
         "securityContext": {
           "runAsUser": 65532,
           "runAsGroup": 65532
         },
         "volumeMounts": [
           {"name": "data", "mountPath": "/var/lib/tuwunel"},
           {"name": "backups", "mountPath": "/var/lib/tuwunel-backups"}
         ]
       }],
       "volumes": [
         {"name": "data", "persistentVolumeClaim": {"claimName": "tuwunel-data"}},
         {"name": "backups", "persistentVolumeClaim": {"claimName": "tuwunel-backup-ssd"}}
       ]}
     }'
   ```

3. Scale the server up:

   ```sh
   kubectl -n matrix scale deploy/tuwunel --replicas=1
   ```

Expected result: the server opens the restored database and serves the accounts and rooms from the backup night.

With both volumes lost, the homeserver starts empty: register a new first account and re-join rooms by alias or invite. Federation re-syncs room history on join.

## Repair

| Symptom | First look |
|---|---|
| Pod restarts, `OOMKilled` | `kubectl -n matrix get pod -o jsonpath` for `lastState.terminated`; the 512 Mi limit is an estimate, see the manifest comment. |
| Sync hangs, `Multi-Attach` events | The strategy must stay `Recreate`; a chart or PR that changes it stalls the rollout. |
| Media uploads fail | `kubectl -n matrix logs deploy/tuwunel` for the S3 provider startup check; wrong keys stop the pod loudly. |
| IRC links answer 404 | The registration `media_path` and the middleware `media-rewrite` must agree; both files say so. |
| `Illegal Instruction` crash | The image digest moved off the v3 variant; re-pin to the amd64 `variant: v3` manifest of the `latest` index. |
| No federation | Run the Federation Tester on `finfra.party`; check the DS record first if DANE errors appear. |
| "Link new device" not supported | Check `auth_metadata` (see tech doc); the OIDC switch needs one pod restart, and a restart mid-linking clears the QR session pool - scan again. |
