# secure-file-share runbook

secure-file-share shares one file with one link (`secure-share.yornik.eu`).
The browser encrypts the file with a hybrid post-quantum key (ML-KEM-1024
encapsulation fused with a 256-bit random value). The server stores
ciphertext. The unlock material lives in the link fragment, which the
browser does not send. Source, CI and releases:
`github.com/Yornik/secure-file-share`.

The app is one stateless replica. Its database is `secure-file-share` on
`shared-pg`, created through a managed role, like the Servarr databases.
Since v0.2 the ciphertext itself is one `<id>.sfs` file per share on the
`secure-file-share-blobs` PVC (truenas-ssd, 10 Gi, Prune=false); Postgres
keeps only the bookkeeping. See
[`../tech/database.md`](../tech/database.md) for the shared-pg pattern.

## Documents

| Document | Read it when |
|---|---|
| `manifests/secure-file-share/` | You change the deployment, the routes or the secrets. |
| `manifests/secure-file-share/pvc-blobs.yaml` | You change the blob volume. |
| `manifests/shared-pg/databases.yaml` | You touch the database of the app. |
| The repo `docs/` upstream | You want the wire format or the threat model. |

## How to check the app

1. Open `https://secure-share.yornik.eu/healthz`. Expect `ok`.
2. Open the site. Expect the upload form.
3. Open `https://secure-share.yornik.eu/s/<id>/meta` for a live share id.
   Expect JSON with `one_time` and `expires_at`.

Expected result: all three answer within a second.

## How to read the upload token

NOTE: The token is a bearer token. Anyone holding it can create shares.
Do not put it in a chat or a ticket.

1. Run `sops -d manifests/secure-file-share/secure-file-share-app.enc.yaml`.
2. Read `SFS_ADMIN_TOKEN`.
3. Paste the token into the "Upload token" field of the upload form.

## How to revoke a share (legal/compliance)

The public API has no deletion path. The control plane on :8081 is the
only door that deletes, and its token is a separate secret.

1. Run `sops -d manifests/secure-file-share/secure-file-share-control
   .enc.yaml` and read `SFS_CONTROL_TOKEN`.
2. Open a port-forward to the pod:
   `kubectl -n secure-file-share port-forward deploy/secure-file-share 8081:8081`.
3. Open `http://localhost:8081`.
4. Paste the control token and the share link. Lookup shows the
   bookkeeping (sizes, times, downloads). Delete removes the row and the
   blob and writes one audit log line.

The fragment of the link is never needed: the control plane reads only
the id half, so the operator stays blind to the content.

## How to rotate the control token

1. Edit `manifests/secure-file-share/secure-file-share-control.enc.yaml`
   with `sops`. Replace `SFS_CONTROL_TOKEN` with `openssl rand -hex 24`.
2. Open a pull request. Merge it.
3. Restart the deployment.

Expected result: the old control token stops working after the restart.

## How to rotate the token

1. Edit `manifests/secure-file-share/secure-file-share-app.enc.yaml` with
   `sops`. Replace `SFS_ADMIN_TOKEN` with `openssl rand -hex 24`.
2. Open a pull request. Merge it.
3. Restart the deployment: `kubectl -n secure-file-share rollout restart
   deployment/secure-file-share`.

Expected result: the old token stops working after the restart.

## How to rotate the database password

WARNING: Rotate both files in one pull request. A mismatch breaks the app
at the next restart.

1. Edit `manifests/shared-pg/role-secure-file-share.enc.yaml` with `sops`.
   Set `password` to the new value.
2. Edit `manifests/secure-file-share/secure-file-share-app.enc.yaml` with
   `sops`. Set the same password in `DATABASE_URL`.
3. Merge the pull request. CNPG reloads the managed role secret.
4. Restart the deployment.

## How to restore the database

The database rides the shared-pg backups: continuous WAL archive plus a
base backup every 3 hours. Follow
[`restore-soiree-pg.md`](restore-soiree-pg.md) with the database name
`secure-file-share`.

## Notes

- A share dies by expiry or by burn. The sweeper removes expired rows (and
  their blob files) hourly; the link is dead the moment `expires_at`
  passes, not when the row goes.
- A URL import reads the plaintext once on the server. That is by design.
  Postgres still never sees anything but bookkeeping, and the volume never
  sees anything but ciphertext.
- The blob PVC is the only state outside Postgres. It holds a rolling
  window (shares live 7 days by default, 90 at most), not an archive; the
  class can expand if the window ever needs to be wider.
- Prometheus scrapes the app through the ServiceMonitor; the Grafana
  dashboard lives in `manifests/secure-file-share/grafana-dashboard.yaml`
  (source of truth: `dashboards/secure-file-share.json` in the app repo).
- The image is `ghcr.io/yornik/secure-file-share`, signed with keyless
  cosign. Renovate opens the version bump; do not pin by hand.
