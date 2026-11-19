# secure-file-share runbook

secure-file-share shares one file with one link (`secure-share.yornik.eu`).
The browser encrypts the file. The server stores ciphertext. The key lives in
the link fragment, which the browser does not send. Source, CI and releases:
`github.com/Yornik/secure-file-share`.

The app is one stateless replica. Its database is `secure-file-share` on
`shared-pg`, created through a managed role, like the Servarr databases. See
[`../tech/database.md`](../tech/database.md) for the shared-pg pattern.

## Documents

| Document | Read it when |
|---|---|
| `manifests/secure-file-share/` | You change the deployment, the routes or the secrets. |
| `manifests/shared-pg/databases.yaml` | You touch the database of the app. |
| The repo `docs/` upstream | You want the wire format or the threat model. |

## How to check the app

1. Open `https://secure-share.yornik.eu/healthz`. Expect `ok`.
2. Open the site. Expect the upload form.
3. Open `https://secure-share.yornik.eu/s/<id>/meta` for a live share id.
   Expect JSON with `one_time` and `expires_at`.

Expected result: all three answer within a second.

## How to read the admin token

NOTE: The token is a bearer token. Anyone holding it can create, list and
revoke shares. Do not put it in a chat or a ticket.

1. Run `sops -d manifests/secure-file-share/secure-file-share-app.enc.yaml`.
2. Read `SFS_ADMIN_TOKEN`.
3. Paste the token into the "Admin token" field of the upload form.

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

- A share dies by expiry or by burn. The sweeper removes expired rows hourly;
  the link is dead the moment `expires_at` passes, not when the row goes.
- A URL import reads the plaintext once on the server. That is by design.
  The database still holds ciphertext only.
- The image is `ghcr.io/yornik/secure-file-share`, signed with keyless
  cosign. Renovate opens the version bump; do not pin by hand.
