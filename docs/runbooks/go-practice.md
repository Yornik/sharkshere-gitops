# Go practice course

The `go-practice` Application serves a web IDE for the Go practice course on `vesper-labs.org`. `go-learn.party`, the old host, redirects to it. A learner writes Go in the browser, and a runner in the cluster runs `go vet`, `staticcheck` and `go test -race` on that code. This file says how to deploy the Application the first time, how to operate it, how it moved to `vesper-labs.org` and what the runner sandbox protects.

| Item | Value |
|---|---|
| Manifests | `manifests/go-practice/` |
| Source | [`Yornik/go-practice-web`](https://github.com/Yornik/go-practice-web). The contract is `docs/DESIGN.md` in that repository. |
| Web server | Deployment `go-practice-web` in namespace `go-practice`. Image `ghcr.io/yornik/go-practice-web`. Site on `:8080`, metrics on `:9090`. |
| Runner | Deployment `go-practice-runner` in namespace `go-practice-runner`. Image `ghcr.io/yornik/go-practice-runner`. API on `:8081`, cluster-internal only. Metrics on `:9091`. |
| Database | SQLite at `/data/go-practice.db` on PVC `go-practice-data-ssd` (`truenas-ssd`, NFS, 2Gi). The app writes 1 backup a day to `/data/backups` and keeps 7. ArgoCD does not prune the PVC (`Prune=false`). |
| Mail | From `HUSH · Vesper Labs <hush@vesper-labs.org>` through Resend. `manifests/external-dns/cronjob-mail-sender-vesper.yaml` publishes the records of Resend. |
| Secrets | `go-practice-web` from `secret-web.enc.yaml`: the runner token and a copy of the Resend API key of soiree. `go-practice-runner` from `secret-runner.enc.yaml`: the same runner token. |
| Public host | `vesper-labs.org`, the apex of its own Cloudflare zone. There is no `www`. `go-learn.party`, the old host and also a zone apex, redirects each path to it. |
| Sign-up | Invite only. The first account comes from a setup link in the log. Login is by passkey only. |

| Document | Content |
|---|---|
| [`../tech/README.md`](../tech/README.md) | Traffic flow, storage classes and the public surface. |
| [`../incidents/grafana-rwo-multi-attach.md`](../incidents/grafana-rwo-multi-attach.md) | Why the web Deployment uses `Recreate`. |
| [`../incidents/2026-09-09-prometheus-release-label-selector.md`](../incidents/2026-09-09-prometheus-release-label-selector.md) | Why each ServiceMonitor has the `release` label. |
| [`../incidents/2026-10-12-truenas-update-readonly-pv-remount.md`](../incidents/2026-10-12-truenas-update-readonly-pv-remount.md) | Why the readiness probe of the web server writes to the database. |
| [`../styleguide.md`](../styleguide.md) | The writing rules for this file. |

WARNING: The runner runs code that any learner with an account sends. The isolation of the runner depends on 2 things: the CNI of the cluster must enforce NetworkPolicy, and the node kernel must have Landlock. The CNI is Flannel, and Flannel does not enforce NetworkPolicy (checked on 2026-10-17). Landlock is then the only network control of learner code. Read [What the runner sandbox does and does not do](#what-the-runner-sandbox-does-and-does-not-do) before you send the first invite.

## How to deploy the first time

Do the steps in this order. Each step needs the step before it.

NOTE: The first deploy put the site on `go-learn.party`. Steps 2, 3 and 6 record how that name was set up. The site moved to `vesper-labs.org` later, see [How to move the site to vesper-labs.org](#how-to-move-the-site-to-vesper-labsorg). The checks of the other steps use `vesper-labs.org`.

### 1. Release the images

`go-practice-web` releases with Release Please. After each push to `main`, its Release workflow keeps a release pull request up to date.

1. In `go-practice-web`, open Settings, Actions, General.
2. Turn on "Allow GitHub Actions to create and approve pull requests". Do this before the first push to `main`. The setting is off by default in a personal account.
3. Open the pull request `chore(main): release 0.1.0`.
4. Merge the pull request. The Release workflow creates the tag `v0.1.0`, runs CI and builds both images.
5. Wait until the `images` job of the Release workflow is green.
6. On GitHub, open the package `go-practice-web`.
7. Open "Package settings".
8. Set the visibility to Public.
9. Do steps 6 to 8 again for the package `go-practice-runner`.
10. Check that a computer without a GHCR login can read each image:

   ```sh
   docker manifest inspect ghcr.io/yornik/go-practice-web:v0.1.0 >/dev/null && echo web ok
   docker manifest inspect ghcr.io/yornik/go-practice-runner:v0.1.0 >/dev/null && echo runner ok
   ```

Expected result: `web ok` and `runner ok`. If you get `unauthorized`, the package is still private, and the cluster cannot pull it.

If a job of the Release run fails after the tag exists, use "Re-run failed jobs". "Re-run all jobs" builds nothing, because Release Please finds no new release. If the run is too old to re-run, run the Release workflow by hand with the tag.

### 2. Prepare the Cloudflare zone

`go-learn.party` is a zone of its own in the same Cloudflare account as `bokings-driessen.party`. ExternalDNS, the CAA job and the no-mail job all use the token in `manifests/external-dns/secret.enc.yaml`.

1. In Cloudflare, make sure that the zone `go-learn.party` has the status Active.
2. Open My Profile, then API Tokens.
3. Edit the token that ExternalDNS uses.
4. If the zone resources do not include `go-learn.party`, add the zone. The token needs Zone Read and DNS Edit.
5. Save the token.

NOTE: Universal SSL adds CAA records for the CAs of Cloudflare to a zone that has a CAA record. The job `caa-updater-go-learn` then fails every week. Each record is DNS only, so the edge certificate has no use. See the comment in `manifests/external-dns/configmap-caa-updater-script.yaml`.

6. In the zone `go-learn.party`, open SSL/TLS, then Edge Certificates.
7. Disable Universal SSL.

### 3. Publish the DNS record before the route

CAUTION: Merge the DNS change before the change that adds the Application. Traefik does not try a failed ACME order again on a timer. It tries again only when its configuration changes. If the IngressRoute exists before `go-learn.party` resolves, the site can stay without a certificate until a restart of Traefik.

NOTE: If 1 pull request holds both changes, the route comes first. Then do [If the site has no valid certificate](#if-the-site-has-no-valid-certificate) after the name resolves.

1. Merge the change to `manifests/external-dns/`. It adds `dns-go-learn-party` and `--domain-filter=go-learn.party`.
2. Wait 5 minutes. ExternalDNS runs every 5 minutes.
3. Read the records from a public resolver:

   ```sh
   dig +short @1.1.1.1 go-learn.party A
   dig +short @1.1.1.1 go-learn.party AAAA
   ```

Expected result: `78.47.240.158` and `77.42.94.152`, then `2a01:4f8:1c19:60c2::1` and `2a01:4f9:c014:e6de::1`.

If the output is empty after 10 minutes, read the log of ExternalDNS:

```sh
kubectl --context yornik-sharkshere -n external-dns logs deploy/external-dns | grep go-learn
```

A line about no matching zone means that the token cannot reach the zone. Do [step 2](#2-prepare-the-cloudflare-zone) again.

### 4. Deploy the Application

NOTE: Copy the Resend API key on the branch of this change before you merge it. Then the web server sends mail from its first start, and step 5 needs no restart. Do steps 1 to 4 of [How to set the Resend API key](#how-to-set-the-resend-api-key), commit the file and push it to the branch.

1. Merge the change that adds `go-practice` to `apps/values.yaml` and `manifests/go-practice/`.
2. Make sure that the Application reports Synced and Healthy in ArgoCD.
3. Read the pods of the web server:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice get pods
   ```

4. Read the pods of the runner:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice-runner get pods
   ```

5. Read the sandbox level and the race detector of the runner:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice-runner logs deploy/go-practice-runner | grep -e 'sandbox for runs' -e 'toolchain ready'
   ```

   Expected result:

   - The `sandbox for runs` line is INFO. Its `sandbox` field starts with `landlock ABI 6` or a higher ABI.
   - The `toolchain ready` line shows `"race":true`.

   If the `sandbox for runs` line is a WARN, runs are not confined. Then invite only people that you trust. For an ABI below 6, see [What the runner sandbox does and does not do](#what-the-runner-sandbox-does-and-does-not-do).

   With seccomp `RuntimeDefault` on Talos, `"race":false` can occur. Tests then run without `-race`. See [Problems](#problems).

   The 2 lines describe the node of the current pod only. Read them again after each release and each Talos upgrade.

6. Read the headers of the site:

   ```sh
   curl -sSI https://vesper-labs.org/ | grep -i -e '^HTTP' -e strict-transport-security
   ```

Expected result: each pod is `1/1 Running`. `curl` shows a `200` and the `strict-transport-security` header. If `curl` reports a certificate error, see [If the site has no valid certificate](#if-the-site-has-no-valid-certificate).

### 5. Create the first account

Every account must verify its email address before the course opens. Set the key first, so that the verification mail reaches you.

1. If `GPW_SMTP_PASSWORD` is still `REPLACE_ME`, do steps 1 to 8 of [How to set the Resend API key](#how-to-set-the-resend-api-key). No account exists yet, so the verification mail in the next step tests the key.
2. Do [How to get the setup link](#how-to-get-the-setup-link).

### 6. Add the host to security.txt

The `security-txt` route in `manifests/traefik-config/` serves `/.well-known/security.txt` on every host, so it also serves `go-learn.party`. At the first deploy, the signed file did not name `go-learn.party` in a `Canonical` line. It does now.

NOTE: The check in step 3 fails on a file that you change without a new signature. For `vesper-labs.org`, see [Sign security.txt with the new host](#sign-securitytxt-with-the-new-host).

1. Add `Canonical: https://go-learn.party/.well-known/security.txt` to `manifests/traefik-config/configmap-security-txt.yaml`.
2. Sign the file again with the security.txt key.
3. Run the check that CI runs:

   ```sh
   .github/scripts/validate-security-txt.sh
   ```

4. Open a pull request with the change.

## How to get the setup link

The web server makes a setup link at start when the database has no user. The link creates the first account, and that account is admin.

WARNING: Anyone who reads the log can create the admin account with this link until you use it. Use the link at once.

NOTE: While no account exists, each start of the web server writes a new setup link, and the old link stops working. Use the link from the log of the current pod only. If you search Loki in Grafana with `{namespace="go-practice"} |= "setup link"`, use the newest line. A link from an earlier pod shows "This setup link does not work any more".

1. Read the link from the log of the web server:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice logs deploy/go-practice-web | grep 'setup link'
   ```

2. Open the link in a browser that can make a passkey.
3. Create the account and the passkey. Use an email address that you can read.
4. Open the link in the verification mail.

Expected result: the verification mail arrives from `HUSH · Vesper Labs <hush@vesper-labs.org>`. The course opens, and the account page shows 1 passkey and a verified address.

If the Resend key is not set yet, the mail is in the log of the web server. Read the link from the log:

```sh
kubectl --context yornik-sharkshere -n go-practice logs deploy/go-practice-web | grep 'mail not sent' | grep -o 'https://vesper-labs.org/verify-email?token=[A-Za-z0-9_-]*'
```

## How to set the Resend API key

While `GPW_SMTP_PASSWORD` is `REPLACE_ME`, the app writes each mail to the log and sends nothing. The setup link works without mail. Learners cannot verify their address, so the course stays closed to them. Recovery by mail and the security notices do not work. Set the key before you send the first invite.

go-practice uses the Resend API key of soiree. go-practice sends from `vesper-labs.org` and soiree from `yornik.eu`, so Resend must allow the key to send from both. A key with Full access, or with Sending access for all domains, can do that. The key is in 2 files: `SMTP_PASSWORD` in `manifests/soiree/soiree-app.enc.yaml` and `GPW_SMTP_PASSWORD` in `manifests/go-practice/secret-web.enc.yaml`. If you rotate the key, change both files in 1 pull request, and restart both web servers.

NOTE: The steps give the key to `sops` on stdin, as in [How to rotate the runner token](#how-to-rotate-the-runner-token). The key does not show on the screen or in the process list. You need the age private key of this repository.

1. Read the key of soiree into a shell variable. Do not print it:

   ```sh
   KEY="$(sops decrypt --extract '["stringData"]["SMTP_PASSWORD"]' manifests/soiree/soiree-app.enc.yaml)"
   ```

2. Write the key to the web Secret, then clear the variable:

   ```sh
   printf '"%s"' "$KEY" | sops set --value-stdin manifests/go-practice/secret-web.enc.yaml '["stringData"]["GPW_SMTP_PASSWORD"]'
   unset KEY
   ```

3. Check that the value is a Resend key. The command prints the first 3 characters only:

   ```sh
   sops decrypt --extract '["stringData"]["GPW_SMTP_PASSWORD"]' manifests/go-practice/secret-web.enc.yaml | cut -c1-3
   ```

   Expected result: `re_`. If you see `REP`, step 2 did not write the key.

4. Check that `sops` encrypted the file:

   ```sh
   sops filestatus manifests/go-practice/secret-web.enc.yaml
   ```

   Expected result: `{"encrypted":true}`. If the result is different, do not commit the file.

5. Open a pull request with the change.
6. Merge the pull request.
7. Make sure that the Application reports Synced in ArgoCD.

CAUTION: The web Deployment uses `Recreate`. The restart in the next step stops the site for some seconds, and each test run in progress ends.

8. Restart the web server. The pod reads the Secret only when it starts:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice rollout restart deploy/go-practice-web
   ```

9. If an admin account exists, send an invite by mail to your own address from the admin page. Then revoke the invite on the admin page. If no account exists yet, the verification mail in step 4 of [How to get the setup link](#how-to-get-the-setup-link) is the test.

Expected result: the mail arrives from `HUSH · Vesper Labs <hush@vesper-labs.org>`.

NOTE: To give go-practice a key of its own later, create a key in Resend with sending access for `vesper-labs.org`. Put it in `KEY` without printing it, and do steps 2 to 9. A key of its own lets you revoke it without an effect on soiree. Then update the notes in both `secret-generator.yaml` files.

## How to release a new version

1. In `go-practice-web`, merge the release pull request, for example `chore(main): release 0.2.0`.
2. Wait until the `images` job of the Release workflow is green. If it fails, see the end of [Release the images](#1-release-the-images).
3. In this repository, wait for the Renovate pull request `go-practice images`. It does not merge itself.
4. Check that the pull request sets `go-practice-web` and `go-practice-runner` to the same tag. If only 1 image changed, wait for the next Renovate run.

CAUTION: The web Deployment uses `Recreate`. The merge in the next step stops the site for some seconds, and each test run in progress ends.

5. Merge the Renovate pull request.
6. Make sure that the Application reports Synced and Healthy in ArgoCD.
7. Wait until the new runner pod is ready:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice-runner rollout status deploy/go-practice-runner
   ```

8. Read the sandbox level and the race detector of the new runner pod. Use the command of step 5 in [Deploy the Application](#4-deploy-the-application).

Expected result: ArgoCD rolls out both Deployments, and each pod is `1/1 Running`. The 2 runner log lines match the expected result of the first deploy.

### A release that migrates the database

Some releases change the database schema. 0.2.0 does: migration 0003 moves the stored progress, code, notes, reveals and certificate kinds to the course of 50 exercises.

- Before the first pending migration, the web server writes a checked copy to `/data/backups/go-practice-before-NNNN.db`, for example `go-practice-before-0003.db`. If it cannot write the copy, it does not start. A web pod that is `1/1 Running` after the release therefore has the copy.
- The daily backups rotate by weekday and never touch this file. It stays until you delete it.
- A migration is one way: the previous image refuses a schema it does not know. To roll back, do [How to restore the database](#how-to-restore-the-database) with `go-practice-before-NNNN.db` as the copy, and set both image tags back to the previous release in the same change.

## How to move the site to vesper-labs.org

The site moves from `go-learn.party` to `vesper-labs.org`. `go-learn.party` stays, and redirects every path to the new name. Old links and the verify links in issued certificates keep working.

The move has 3 changes, in this order. The DNS change goes first, because Traefik does not try a failed ACME order again on a timer (see [step 3 of the first deploy](#3-publish-the-dns-record-before-the-route)). The certificate change goes before the route change. If its ACME order fails, `go-learn.party` still serves the site. The route change needs the images of go-practice-web v0.3.0 or later, from their own Renovate pull request, merged before it.

| Change | What it does |
|---|---|
| DNS | `manifests/external-dns/`: the dummy Service `dns-vesper-labs-org`, `--domain-filter=vesper-labs.org`, and the jobs `caa-updater-vesper` and `mail-sender-vesper`. Nothing serves the name yet, and nothing sends from it yet. |
| Certificate | `manifests/go-practice/`: a temporary route for `vesper-labs.org` that redirects to `go-learn.party`, so that Traefik gets the certificate of the new name. `manifests/external-dns/`: the job `dane-updater-vesper`, and a guard in the DANE script. The site stays on `go-learn.party`. |
| Route | `manifests/go-practice/`: the routes for `vesper-labs.org`, the redirect from `go-learn.party`, `GPW_PUBLIC_URL=https://vesper-labs.org`, `GPW_MOVED_FROM=go-learn.party` and `GPW_MAIL_FROM` on `vesper-labs.org`. It removes the temporary route of the certificate change. |

CAUTION: A passkey belongs to 1 domain. After the route change, the passkeys made on `go-learn.party` do not work on `vesper-labs.org`. Each person signs in once with account recovery by email, and makes a new passkey. Progress, code and certificates stay, because they belong to the account, not to the passkey. Tell the learners before you merge the route change.

### 1. Prepare the zone

1. In Cloudflare, make sure that the zone `vesper-labs.org` has the status Active.
2. Open My Profile, then API Tokens.
3. Edit the token that ExternalDNS uses.
4. Add the zone `vesper-labs.org` to its zone resources, with Zone Read and DNS Edit.
5. Save the token.
6. In the zone `vesper-labs.org`, open SSL/TLS, then Edge Certificates.
7. Disable Universal SSL. The reason is in the note of [step 2 of the first deploy](#2-prepare-the-cloudflare-zone).
8. In Resend, open Domains.
9. If `vesper-labs.org` is not in the list, add it in the region of `yornik.eu`.
10. Open `vesper-labs.org` and compare its records with the job in `manifests/external-dns/cronjob-mail-sender-vesper.yaml`. The table below lists them.
11. If a value differs, change it in the job.
12. Open API Keys.
13. If the key in `manifests/go-practice/secret-web.enc.yaml` can send only from `yornik.eu`, make a key that can send from `vesper-labs.org`.
14. If you made a new key, do [How to set the Resend API key](#how-to-set-the-resend-api-key) with it.

| Record in Resend | Variable in the job | Value on 21 October 2026 |
|---|---|---|
| CNAME `send` | `RESEND_RETURN_PATH` | `send.forge.rmta.net` |
| CNAME `rsend` | `RESEND_FALLBACK_PATH` | `rsend-euw1.forge.rmta.net` |
| TXT `resend._domainkey` | `RESEND_DKIM` | `p=MIGfMA0GCSqGSIb3DQEB…` |
| MX at the apex | `RESEND_INBOUND_MX` | `receive-euw1.forge.rmta.net`, priority 10 |

NOTE: Resend's Cloudflare setup writes these records into the zone. The job takes them over and does not add a second copy. If Resend shows MX and TXT records on `send` instead of a CNAME, the script does not fit that layout: see its comment.

### 2. Merge the DNS change

1. Merge the change to `manifests/external-dns/`.
2. Wait 5 minutes. ExternalDNS runs every 5 minutes.
3. Read the records from a public resolver:

   ```sh
   dig +short @1.1.1.1 vesper-labs.org A
   dig +short @1.1.1.1 vesper-labs.org AAAA
   ```

Expected result: `78.47.240.158` and `77.42.94.152`, then `2a01:4f8:1c19:60c2::1` and `2a01:4f9:c014:e6de::1`.

If the output is empty after 10 minutes, read the log of ExternalDNS:

```sh
kubectl --context yornik-sharkshere -n external-dns logs deploy/external-dns | grep vesper
```

A line about no matching zone means that the token cannot reach the zone. Do [step 1](#1-prepare-the-zone) again.

### 3. Check the mail records

The jobs `caa-updater-vesper` and `mail-sender-vesper` run on Sunday morning.

1. After the first Sunday, read the records:

   ```sh
   dig +short @1.1.1.1 vesper-labs.org CAA
   dig +short @1.1.1.1 vesper-labs.org TXT
   dig +short @1.1.1.1 _dmarc.vesper-labs.org TXT
   dig +short @1.1.1.1 vesper-labs.org MX
   dig +short @1.1.1.1 send.vesper-labs.org CNAME
   dig +short @1.1.1.1 rsend.vesper-labs.org CNAME
   dig +short @1.1.1.1 resend._domainkey.vesper-labs.org TXT
   ```

2. In Resend, make sure that `vesper-labs.org` shows Verified.

Expected result:

- The CAA records allow only Let's Encrypt.
- The SPF record of the zone is `v=spf1 -all`, because Resend sends with `send.vesper-labs.org` as the bounce address.
- The DMARC policy is `p=none` with reports to `dmarcreports@vesper-labs.org`: Resend's starting policy. Raise it to `p=quarantine`, as for `yornik.eu`, once the reports show only Resend sending as the zone.
- The MX is `10 receive-euw1.forge.rmta.net`, so replies to `hush@vesper-labs.org` reach Resend.
- `send`, `rsend` and the DKIM key have the values of the table in step 1.

### 4. Get the certificate of vesper-labs.org

The certificate change gets the Let's Encrypt certificate of `vesper-labs.org` while the site stays on `go-learn.party`. It does these things:

- The temporary route `vesper-labs-temporary` on `websecure` makes Traefik order the certificate of `vesper-labs.org`. Traefik stores it in `acme.json`, and the route change uses it.
- Each request to `https://vesper-labs.org` goes to the same path and query on `https://go-learn.party`, except the 2 paths of security.txt below. Traefik answers 302 to GET and 307 to every other method. A browser does not keep these answers, so the route change can turn the direction around.
- `/.well-known/security.txt` and `/.well-known/pgp-key.txt` are not redirected. The `security-txt` route serves them on every host, with priority 9999. From the certificate change to the route change, the signed file has no `Canonical` line for `vesper-labs.org`. RFC 9116 tells a reader not to trust such a file, so a security.txt scanner can report this host. The route change adds the line.
- The app gets no request from `vesper-labs.org`. Its WebAuthn relying party and its Origin check stay `go-learn.party` until the route change.
- `go-learn.party` does not change.
- The job `dane-updater-vesper` publishes the TLSA record `_443._tcp.vesper-labs.org` each night at 03:43 UTC.
- The DANE script of all DANE jobs stops, and keeps the record, if a host serves no certificate. Before this change, it published the hash of empty input.

NOTE: Let's Encrypt validates the order with HTTP-01 on port 80. The challenge router of Traefik has priority `MaxInt`, above the redirection of the `web` entry point at `MaxInt - 1`. So the challenge path is not redirected. Step 2 of [Before the certificate change](#before-the-certificate-change) shows that port 80 of the name reaches that router.

#### Before the certificate change

1. Make sure that `vesper-labs.org` resolves. Use the commands of [step 2](#2-merge-the-dns-change).
2. Request an unknown challenge token on the new name:

   ```sh
   curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' http://vesper-labs.org/.well-known/acme-challenge/cert-precheck
   ```

   Expected result: `404 0`. The challenge handler answers an unknown token with an empty 404. If you get a `301`, a `308` or an error, do not merge. Find out why the challenge path does not reach Traefik.

#### Merge the certificate change

NOTE: No pod restarts. The change adds an IngressRoute, a Middleware and a CronJob, and changes the ConfigMap of the DANE script.

1. Merge the pull request.
2. Make sure that the Applications `go-practice` and `external-dns` report Synced and Healthy in ArgoCD.
3. Wait 1 minute. Traefik orders the certificate after the sync.

#### Checks after the certificate change

1. Read the certificate of the new host:

   ```sh
   echo | openssl s_client -connect vesper-labs.org:443 -servername vesper-labs.org 2>/dev/null | openssl x509 -noout -text | grep -e 'Issuer:' -e 'DNS:' -e 'Not After'
   ```

   Expected result: an issuer with `O=Let's Encrypt`, `DNS:vesper-labs.org` and a `Not After` date about 90 days ahead. If `openssl` cannot load a certificate, the order failed. Do [If the order failed](#if-the-order-failed).

2. Read the temporary redirect of a GET with a path and a query:

   ```sh
   curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' 'https://vesper-labs.org/guide?from=cert-check'
   ```

   Expected result: `302 https://go-learn.party/guide?from=cert-check`.

3. Read the headers of the redirect:

   ```sh
   curl -sSI https://vesper-labs.org/ | grep -i -e '^HTTP' -e '^location' -e '^cache-control' -e strict-transport-security
   ```

   Expected result: `HTTP/2 307`, `location: https://go-learn.party/` and the `strict-transport-security` header. No `cache-control` line shows, so no browser keeps the redirect. The status is 307 because `curl -I` sends HEAD.

4. Follow the redirect from http to the end:

   ```sh
   curl -sSL -o /dev/null -w '%{http_code} %{num_redirects} %{url_effective}\n' 'http://vesper-labs.org/guide?from=cert-check'
   ```

   Expected result: `200 2 https://go-learn.party/guide?from=cert-check`. The redirection of the web entry point answers first and sends the request to `https://vesper-labs.org`. The second redirect goes to `go-learn.party`.

5. Read the headers of the old host:

   ```sh
   curl -sSI https://go-learn.party/ | grep -i -e '^HTTP' -e strict-transport-security
   ```

   Expected result: `HTTP/2 200` and the `strict-transport-security` header, with no certificate error. `go-learn.party` did not change.

NOTE: The job runs each night at 03:43 UTC. Steps 6 to 8 start a run at once. The Job of step 6 is not in git. ArgoCD does not prune it, and it deletes itself after 1 day. If you wait for the night, skip steps 6 to 8.

6. Start a run of the job:

   ```sh
   kubectl --context yornik-sharkshere -n external-dns create job --from=cronjob/dane-updater-vesper dane-updater-vesper-first
   ```

7. Wait until the run ends:

   ```sh
   kubectl --context yornik-sharkshere -n external-dns wait --for=condition=complete --timeout=3m job/dane-updater-vesper-first
   ```

   Expected result: `job.batch/dane-updater-vesper-first condition met`. If the command times out, the run failed. Step 8 shows why.

8. Read the log of the run:

   ```sh
   kubectl --context yornik-sharkshere -n external-dns logs job/dane-updater-vesper-first
   ```

   Expected result: the log ends with `TLSA update succeeded`.

NOTE: Step 9 asks a name server of the zone, not a public resolver. A resolver keeps an empty answer for up to 30 minutes, the negative TTL in the SOA of the zone. If somebody asked for the record before the run, a resolver can still show no record.

9. Read the TLSA record from a name server of the zone:

   ```sh
   dig +short @vick.ns.cloudflare.com _443._tcp.vesper-labs.org TLSA
   ```

10. Compute the hash of the key that the host serves:

    ```sh
    echo | openssl s_client -connect vesper-labs.org:443 -servername vesper-labs.org 2>/dev/null | openssl x509 -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256 | awk '{print toupper($NF)}'
    ```

    Expected result: step 9 shows `3 1 1` and the 64 hex characters of step 10. `dig` can split the hex into 2 groups.

11. Make sure that DNSSEC signs the record:

    ```sh
    dig +dnssec @1.1.1.1 _443._tcp.vesper-labs.org TLSA | grep 'flags:'
    ```

    Expected result: the first line has the flag `ad` and `ANSWER: 2`, the record and its signature. An empty answer also has `ad`. If you get `ANSWER: 0`, the resolver still holds the empty answer from before the run. Wait 30 minutes, then do this step again.

If step 9 shows no record, do these steps:

1. List the runs of the job:

   ```sh
   kubectl --context yornik-sharkshere -n external-dns get jobs | grep dane-updater-vesper
   ```

2. Read the log of the last run. Replace `<job>` with its name:

   ```sh
   kubectl --context yornik-sharkshere -n external-dns logs job/<job>
   ```

A log line with `it served no certificate` means that the host served no certificate at the time of the run. The job did not change the record. See [Problems](#problems).

#### If the order failed

If `openssl` in step 1 of the checks loads no certificate, the ACME order failed. Only the temporary redirect on `vesper-labs.org` has no certificate. `go-learn.party` still serves the site with its own certificate.

Traefik does not try the order again on a timer. It tries again each time its configuration changes. While the cause stays, each of these tries fails too, and Let's Encrypt counts it.

WARNING: Do not merge the route change while `vesper-labs.org` has no certificate. The redirect of `go-learn.party` then sends every learner to a name that has no certificate.

1. Read the error of the order in the log of Traefik:

   ```sh
   kubectl --context yornik-sharkshere -n traefik logs deploy/traefik | grep 'Unable to obtain ACME certificate' | grep vesper-labs.org
   ```

2. Do [If the site has no valid certificate](#if-the-site-has-no-valid-certificate). It fixes the cause before it restarts Traefik.
3. Do the [checks after the certificate change](#checks-after-the-certificate-change) again.

### 5. Merge the route change

The route change does these things:

- `vesper-labs.org` serves the site on `websecure`, with the certificate of [step 4](#4-get-the-certificate-of-vesper-labsorg) and the middlewares of the old host. Its `web` route redirects to https.
- The temporary route of step 4 goes away, with its redirect to `go-learn.party`.
- `go-learn.party` keeps its routes on `web` and `websecure`, and its certificate. Each request goes to the same path and query on `https://vesper-labs.org`. Traefik answers 301 to GET and 308 to every other method, so a POST keeps its method and its body. The redirect has `Cache-Control: max-age=3600`.
- The web server gets `GPW_PUBLIC_URL=https://vesper-labs.org`, `GPW_MOVED_FROM=go-learn.party` and `GPW_MAIL_FROM="HUSH · Vesper Labs <hush@vesper-labs.org>"`. The sign-in and recovery pages then say that the site moved, and that a passkey made on `go-learn.party` does not work here.

WARNING: Do not merge the route change before the images run v0.3.0 or later. An older release refuses `GPW_MOVED_FROM`, and the web server does not start.

WARNING: Do not put the image bump and the route change in 1 pull request. A revert of that pull request also sets the images back. v0.2.0 migrates the database one way, so an older image refuses the database, and the web server does not start. See [A release that migrates the database](#a-release-that-migrates-the-database).

#### Before the merge

1. Make sure that both Deployments run v0.3.0 or later:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice get deploy go-practice-web -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   kubectl --context yornik-sharkshere -n go-practice-runner get deploy go-practice-runner -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   ```

   Expected result: both tags are `v0.3.0` or later. If a tag is older, do [How to release a new version](#how-to-release-a-new-version) with the Renovate pull request `go-practice images` first.

2. Make sure that the web pod is `1/1 Running`:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice get pods
   ```

NOTE: The route change uses the certificate that Traefik got in [step 4](#4-get-the-certificate-of-vesper-labsorg). Traefik starts no ACME order for it.

3. Make sure that `vesper-labs.org` serves its certificate:

   ```sh
   echo | openssl s_client -connect vesper-labs.org:443 -servername vesper-labs.org 2>/dev/null | openssl x509 -noout -text | grep -e 'Issuer:' -e 'DNS:' -e 'Not After'
   ```

   Expected result: an issuer with `O=Let's Encrypt`, `DNS:vesper-labs.org` and a `Not After` date in the future. If `openssl` cannot load a certificate, do not merge. Do [step 4](#4-get-the-certificate-of-vesper-labsorg) first.

4. Make sure that steps 9 to 11 of [Checks after the certificate change](#checks-after-the-certificate-change) passed. They check the TLSA record of `vesper-labs.org`.

   If you did not do them, do them now. They need a run of the job after the certificate change: steps 6 to 8 there, or the run at 03:43 UTC. If the record is missing or does not match, do not merge.

5. In Resend, open Domains. Make sure that `vesper-labs.org` shows Verified.
6. Open API Keys. Make sure that the key of go-practice has Full access, or Sending access for all domains or for `vesper-labs.org`.

NOTE: Step 7 sends a real mail with the key of go-practice. The header goes to `curl` on stdin, so the key does not show in the process list.

7. Send a test mail from the new sender to an address that you read. Replace `you@example.com`:

   ```sh
   KEY="$(sops decrypt --extract '["stringData"]["GPW_SMTP_PASSWORD"]' manifests/go-practice/secret-web.enc.yaml)"
   printf 'Authorization: Bearer %s\n' "$KEY" | curl -sS https://api.resend.com/emails -H @- -H 'Content-Type: application/json' \
     --data '{"from":"HUSH · Vesper Labs <hush@vesper-labs.org>","to":["you@example.com"],"subject":"Recover your account","text":"A test of the new sender. https://vesper-labs.org/recover"}'
   unset KEY
   ```

   Expected result: `{"id":"…"}`. If Resend answers with an error that names the domain, do steps 5 and 6 again.

8. Open the mail. Make sure that it is in the inbox, not in the spam folder.
9. Open the headers of the mail. In Gmail, select "Show original".

   Expected result: SPF, DKIM and DMARC show `PASS`. DKIM signs for `vesper-labs.org`.

   If the mail is in the spam folder, do not merge yet. A new domain gets a reputation over days. Do steps 7 to 9 again later. Each learner needs the recovery mail after the move.

10. Do [Sign security.txt with the new host](#sign-securitytxt-with-the-new-host) on the branch of the route change.
11. Make sure that the checks of the pull request are green.
12. Tell the learners. Send the text below on the channel that they read:

    ```text
    Go Practice moves to https://vesper-labs.org on <date>.
    Your account, your progress and your certificates move with it.
    Close your tabs of go-learn.party before then. After the move, an open tab cannot save your code.
    Your passkey for go-learn.party does not work on the new site.
    Sign in once with "Recover your account" on https://vesper-labs.org/recover.
    The recovery mail comes from hush@vesper-labs.org. If it is not in your inbox, look in your spam folder.
    Old links and the links in your certificates keep working.
    ```

#### Sign security.txt with the new host

The `security-txt` route in `manifests/traefik-config/` serves `/.well-known/security.txt` on every host, with priority 9999. It serves `vesper-labs.org` since the certificate change of [step 4](#4-get-the-certificate-of-vesper-labsorg). On `go-learn.party` the file is served too, not redirected. The signed file has no `Canonical` line for `vesper-labs.org` yet. The new line is:

```text
Canonical: https://vesper-labs.org/.well-known/security.txt
```

NOTE: You need the private key of `FediShark Security <yornik@yornik.nl>`, fingerprint `3045 A439 1BA8 3006 D0EE E407 EDFB 3085 4A42 B3F0`. CI checks the signature, so a change without a new signature fails the check.

1. Set 2 variables for the next steps:

   ```sh
   W="$(mktemp -d)"
   F=manifests/traefik-config/configmap-security-txt.yaml
   ```

2. Write the signed file to the work directory:

   ```sh
   awk '$0 == "  security.txt: |" {f=1; next} f && /^  [^ ]/ {exit} f {print substr($0, 5)}' "$F" > "$W/security.txt.asc"
   ```

3. Check the signature and write the text without it:

   ```sh
   gpg --decrypt "$W/security.txt.asc" > "$W/security.txt"
   ```

   Expected result: `Good signature from "FediShark Security <yornik@yornik.nl>"`.

4. Add the line after the last `Canonical` line:

   ```sh
   printf '%s\n' 'Canonical: https://vesper-labs.org/.well-known/security.txt' >> "$W/security.txt"
   ```

5. Sign the text:

   ```sh
   gpg --local-user 3045A4391BA83006D0EEE407EDFB30854A42B3F0 --digest-algo SHA256 --clearsign --output "$W/security.txt.new.asc" "$W/security.txt"
   ```

6. Put the signed text in the ConfigMap, indented by 4 spaces:

   ```sh
   awk -v new="$W/security.txt.new.asc" '
     $0 == "  security.txt: |" { print; while ((getline l < new) > 0) print (l == "" ? "" : "    " l); skip = 1; next }
     skip && /^  [^ ]/ { skip = 0 }
     !skip { print }
   ' "$F" > "$W/configmap.yaml"
   cp "$W/configmap.yaml" "$F"
   ```

7. Run the check that CI runs:

   ```sh
   .github/scripts/validate-security-txt.sh
   ```

   Expected result: `security.txt signature and required fields are valid`.

8. Read the change:

   ```sh
   git diff -- "$F"
   ```

   Expected result: 1 new `Canonical` line and a new signature block. Nothing else changes.

9. Commit the file.
10. Push the commit to the branch of the route change.

#### Merge

CAUTION: The web Deployment uses `Recreate`. The merge stops the site for some seconds, and each test run in progress ends.

1. Merge the pull request.
2. Make sure that the Applications `go-practice`, `external-dns` and `traefik-config` report Synced and Healthy in ArgoCD. `traefik-config` changes because of the new signature of security.txt.
3. Wait until the new web pod is ready:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice rollout status deploy/go-practice-web
   ```

4. Read the 3 variables of the web Deployment:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice get deploy go-practice-web -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' | grep -e GPW_PUBLIC_URL -e GPW_MOVED_FROM -e GPW_MAIL_FROM
   ```

   Expected result: `GPW_PUBLIC_URL=https://vesper-labs.org`, `GPW_MOVED_FROM=go-learn.party` and `GPW_MAIL_FROM=HUSH · Vesper Labs <hush@vesper-labs.org>`.

#### Checks after the deploy

1. Read the certificate of the new host:

   ```sh
   echo | openssl s_client -connect vesper-labs.org:443 -servername vesper-labs.org 2>/dev/null | openssl x509 -noout -text | grep -e 'Issuer:' -e 'DNS:' -e 'Not After'
   ```

   Expected result: the issuer and the `Not After` date of step 3 in [Before the merge](#before-the-merge). If `openssl` cannot load a certificate, do [If the site has no valid certificate](#if-the-site-has-no-valid-certificate).

2. Read the certificate of the old host:

   ```sh
   echo | openssl s_client -connect go-learn.party:443 -servername go-learn.party 2>/dev/null | openssl x509 -noout -text | grep -e 'DNS:' -e 'Not After'
   ```

   Expected result: `DNS:go-learn.party` and a `Not After` date in the future.

3. Read the headers of the site:

   ```sh
   curl -sSI https://vesper-labs.org/ | grep -i -e '^HTTP' -e strict-transport-security
   ```

   Expected result: `HTTP/2 200` and the `strict-transport-security` header.

4. Read the readiness of the web server:

   ```sh
   curl -sS https://vesper-labs.org/readyz
   ```

   Expected result: `ok`.

5. Read the redirect of a GET with a path and a query:

   ```sh
   curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' 'https://go-learn.party/guide?from=move-check'
   ```

   Expected result: `301 https://vesper-labs.org/guide?from=move-check`.

6. Read the redirect of a POST:

   ```sh
   curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' -X POST --data '{}' 'https://go-learn.party/api/auth/move-check?from=move-check'
   ```

   Expected result: `308 https://vesper-labs.org/api/auth/move-check?from=move-check`.

7. Follow the redirect from http to the end:

   ```sh
   curl -sSL -o /dev/null -w '%{http_code} %{num_redirects} %{url_effective}\n' 'http://go-learn.party/guide?from=move-check'
   ```

   Expected result: `200 2 https://vesper-labs.org/guide?from=move-check`. The redirection of the web entry point answers first and sends the request to `https://go-learn.party`. The second redirect goes to `vesper-labs.org`.

8. Read the headers of the redirect:

   ```sh
   curl -sSI https://go-learn.party/ | grep -i -e '^HTTP' -e '^location' -e '^cache-control' -e strict-transport-security
   ```

   Expected result: `HTTP/2 308`, `location: https://vesper-labs.org/`, `cache-control: max-age=3600` and the `strict-transport-security` header. The status is 308 because `curl -I` sends HEAD.

9. Read security.txt on both hosts:

   ```sh
   curl -sS https://vesper-labs.org/.well-known/security.txt | grep -c '^Canonical: https://vesper-labs.org/'
   curl -sS -o /dev/null -w '%{http_code}\n' https://go-learn.party/.well-known/security.txt
   ```

   Expected result: `1`, then `200`. The kubelet updates the file in the `security-txt` pod up to about 1 minute after the sync. If the count is `0`, wait 1 minute and run the first command again.

10. Read the move note on the sign-in page:

    ```sh
    curl -sS https://vesper-labs.org/login | grep -c 'go-learn.party'
    ```

    Expected result: a number above `0`.

11. Open `https://vesper-labs.org/login` in a browser. The recovery of your own account in the next steps is the test mail.
12. Make sure that the page says that Go Practice moved from `go-learn.party`.
13. Select "Recover your account".
14. Enter the address of your admin account.
15. Open the mail.

    Expected result: the mail comes from `HUSH · Vesper Labs <hush@vesper-labs.org>`. It is in the inbox.

16. Open the link in the mail. It starts with `https://vesper-labs.org/recover/confirm`.
17. Make a new passkey.

    Expected result: the course opens with your progress. The account page shows the new passkey.

NOTE: The TLSA record of `vesper-labs.org` does not change. The certificate and its key stay the same. Step 4 of [Before the merge](#before-the-merge) checked the record.

#### How to roll back the route change

Roll back the route change only. Keep the images. v0.3.0 also runs with the settings of `go-learn.party`. An image before v0.2.0 refuses the migrated database.

Keep the DNS change and the job `dane-updater-vesper`. The rollback brings back the temporary route of [step 4](#4-get-the-certificate-of-vesper-labsorg). `vesper-labs.org` then redirects to `go-learn.party` again, with the same certificate, so the TLSA record stays correct.

CAUTION: After the rollback, the passkeys made on `vesper-labs.org` do not work on `go-learn.party`. The passkeys made on `go-learn.party` work again. A learner who removed the old passkeys during recovery, or who joined after the move, recovers the account again. Tell the learners.

NOTE: A browser keeps the redirect of `go-learn.party` for up to 1 hour (`Cache-Control: max-age=3600`). Until then, such a browser goes to `vesper-labs.org`, gets the temporary redirect back, and shows an error for too many redirects. A browser without the stored redirect goes to `go-learn.party`.

1. Find the merge commit of the route change. It is the oldest commit on `main` that changed `ingressroute-go-learn.yaml`:

   ```sh
   git fetch origin
   git log --oneline --first-parent origin/main -- manifests/go-practice/ingressroute-go-learn.yaml | tail -n 1
   ```

2. Make a branch from `origin/main`:

   ```sh
   git switch -c rollback-vesper-labs-route origin/main
   ```

3. Put `manifests/go-practice/` back to the state before the merge. Replace `<merge>` with the commit of step 1:

   ```sh
   git restore --source='<merge>^1' --staged --worktree -- manifests/go-practice/
   ```

4. Read the change:

   ```sh
   git diff --staged --stat
   ```

   Expected result: the 4 files `ingressroute-go-learn.yaml`, `ingressroute-go-learn-web.yaml`, `middleware-redirect-vesper-labs.yaml` and `middleware-redirect-cache.yaml` are deleted. The 2 files `ingressroute-vesper-labs-temporary.yaml` and `middleware-redirect-go-learn.yaml` come back. `deployment-web.yaml`, `ingressroute.yaml`, `ingressroute-web.yaml`, `kustomization.yaml` and `service-web.yaml` change.

5. Make sure that no image tag changes:

   ```sh
   git diff --staged -- manifests/go-practice/ | grep 'image:'
   ```

   Expected result: no output. If a line shows, a later image bump is in the diff. Set that tag back to the tag on `origin/main`.

CAUTION: The web Deployment uses `Recreate`. The merge in the next step stops the site for some seconds.

6. Open a pull request with the change.
7. Merge the pull request.
8. Wait until the new web pod is ready:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice rollout status deploy/go-practice-web
   ```

9. Read the readiness of the old host:

   ```sh
   curl -sS https://go-learn.party/readyz
   ```

Expected result: `ok`. A passkey made on `go-learn.party` signs in there again.

## How to rotate the runner token

If the token leaked outside the cluster, rotate it. The 2 Secrets hold the same value. Change both in 1 pull request.

NOTE: The token lets a caller run code on the runner, and nothing more. Learner code in the runner pod can read the token only when the runner has no Landlock sandbox (a WARN `sandbox for runs` line). See [What the runner sandbox does and does not do](#what-the-runner-sandbox-does-and-does-not-do).

1. Make a new token in a shell variable. Do not print it:

   ```sh
   TOKEN="$(openssl rand -hex 32)"
   ```

NOTE: Steps 2 and 3 give the token to `sops` on stdin. A token in a command argument is visible in the process list. `printf` is a shell builtin, so it starts no process.

2. Write the token to the web Secret:

   ```sh
   printf '"%s"' "$TOKEN" | sops set --value-stdin manifests/go-practice/secret-web.enc.yaml '["stringData"]["GPW_RUNNER_TOKEN"]'
   ```

3. Write the token to the runner Secret:

   ```sh
   printf '"%s"' "$TOKEN" | sops set --value-stdin manifests/go-practice/secret-runner.enc.yaml '["stringData"]["GPR_TOKEN"]'
   ```

4. Clear the variable:

   ```sh
   unset TOKEN
   ```

5. Open a pull request with the 2 files.
6. Merge the pull request.
7. Make sure that the Application reports Synced in ArgoCD.

NOTE: Between step 8 and step 9 the 2 pods hold different tokens. The runner answers each call with 401, and the IDE reports that the runner is down. The fault ends when the web pod is ready.

CAUTION: The web Deployment uses `Recreate`. Step 9 stops the site for some seconds, and each test run in progress ends.

8. Restart the runner:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice-runner rollout restart deploy/go-practice-runner
   ```

9. Restart the web server:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice rollout restart deploy/go-practice-web
   ```

10. Run the tests of 1 exercise in the IDE.

Expected result: the test run starts and ends with a result.

## How to restore the database

The app writes a copy of the database to `/data/backups` each day with `VACUUM INTO`, and keeps 7 copies. This procedure puts 1 copy back.

WARNING: The restore replaces the database. Accounts, passkeys, saved code and progress after the time of the copy are lost.

ArgoCD reverts a change made by hand, so `kubectl scale` does not stop the web server. Stop it in git.

### 1. Stop the web server

1. In `manifests/go-practice/deployment-web.yaml`, set `replicas: 0`.
2. Open a pull request with the change.
3. Merge the pull request.
4. Wait until the namespace has no pod:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice get pods
   ```

Expected result: `No resources found in go-practice namespace.`

### 2. Start a helper pod

CAUTION: Do not start the helper pod while the web pod runs. 2 processes that write 1 SQLite file on NFS can damage it.

1. Create the helper pod. The namespace enforces the restricted profile, so the pod spec sets each field that the profile needs:

   ```sh
   kubectl --context yornik-sharkshere apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: go-practice-restore
     namespace: go-practice
   spec:
     restartPolicy: Never
     automountServiceAccountToken: false
     securityContext:
       runAsNonRoot: true
       runAsUser: 65532
       runAsGroup: 65532
       seccompProfile:
         type: RuntimeDefault
     containers:
       - name: restore
         image: keinos/sqlite3:3.53.4
         command: ["sleep", "3600"]
         securityContext:
           allowPrivilegeEscalation: false
           capabilities:
             drop: ["ALL"]
         volumeMounts:
           - name: data
             mountPath: /data
     volumes:
       - name: data
         persistentVolumeClaim:
           claimName: go-practice-data-ssd
   EOF
   ```

2. Wait until the pod is ready:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice wait --for=condition=Ready pod/go-practice-restore --timeout=120s
   ```

### 3. Put the copy back

1. List the database and the copies:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice exec go-practice-restore -- ls -l /data /data/backups
   ```

2. Choose the copy by its date. Write down its name.
3. Keep the current database:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice exec go-practice-restore -- cp /data/go-practice.db /data/go-practice.db.before-restore
   ```

NOTE: SQLite applies a journal file that it finds next to the database. A journal of the old database damages the restored copy.

4. If step 1 showed `go-practice.db-journal`, move it away:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice exec go-practice-restore -- mv /data/go-practice.db-journal /data/go-practice.db-journal.before-restore
   ```

5. Copy the backup over the database. Use the name from step 2:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice exec go-practice-restore -- cp /data/backups/<name> /data/go-practice.db
   ```

6. Check the restored database:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice exec go-practice-restore -- sqlite3 /data/go-practice.db 'PRAGMA integrity_check;'
   ```

   Expected result: `ok`. If the result is different, do steps 5 and 6 again with an older copy.

7. Delete the helper pod:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice delete pod go-practice-restore
   ```

### 4. Start the web server

1. In `manifests/go-practice/deployment-web.yaml`, set `replicas: 1`.
2. Open a pull request with the change.
3. Merge the pull request.
4. Wait until the pod is ready:

   ```sh
   kubectl --context yornik-sharkshere -n go-practice rollout status deploy/go-practice-web
   ```

5. Log in on `https://vesper-labs.org`.

Expected result: the dashboard shows the progress at the time of the copy.

NOTE: If `/data/backups` is lost too, restore the dataset from the ZFS snapshot on TrueNAS. The NAS takes a snapshot at 00:00 each day. The volume handle of the PersistentVolume names the dataset:

```sh
kubectl --context yornik-sharkshere get pv "$(kubectl --context yornik-sharkshere -n go-practice get pvc go-practice-data-ssd -o jsonpath='{.spec.volumeName}')" -o jsonpath='{.spec.csi.volumeHandle}{"\n"}'
```

## What the runner sandbox does and does not do

The runner runs code that we did not write. The table says what each layer gives. The source repository describes the app side in `docs/DESIGN.md`, section "Sandbox rules".

| Layer | What it does |
|---|---|
| Request check | The runner accepts only the stub file names of the exercise. Learner code cannot replace a test file. A file is 256 KiB at most, a request 1 MiB at most. |
| Work directory | Each request gets a new directory under `/tmp/runs`. The runner deletes it when the request ends. |
| Process | `go` runs in its own process group with a small environment: `GOPROXY=off`, `GOTOOLCHAIN=local` and a proxy address that goes nowhere. |
| Landlock, files and processes | Each run starts confined by Landlock. A run can write only its own work directory and the caches. Other runs, the course and the rest of `/tmp` are closed to it. A run cannot trace `tini` or the runner. It cannot read their memory or environment, so it cannot read the runner token. |
| Landlock, network and signals | With ABI 4 (Linux 6.7) or later, a run connects over TCP only to ephemeral ports. The runner API and the Kubernetes API are then out of reach. UDP is not covered. With ABI 6 (Linux 6.12) or later, a run cannot send a signal to `tini` or the runner. The node kernel sets the ABI. The runner logs it at start in the `sandbox for runs` line. |
| Time and output | The runner kills the process group after 40 s for tests, after 20 s for checks, or after 1 MiB of output. |
| Pod | UID 65532, no capabilities, no privilege escalation, seccomp `RuntimeDefault`, read-only root filesystem, no service account token. The namespace enforces the restricted profile. |
| Resources | 2 CPU, 5 GiB of memory, 1 GiB of `/tmp` and 4 GiB of `/cache`. Both volumes are on the disk of the node, not in memory. Past a limit, the kernel kills the container or the kubelet evicts the pod. |
| Namespace | The only Secret in `go-practice-runner` is the runner token. The web Secrets and the database are in `go-practice`. |
| NetworkPolicy | No egress. Ingress only from the web pod to `:8081` and from `monitoring` to `:9091`. Flannel does not enforce it, so it has no effect until the cluster gets a CNI that enforces NetworkPolicy. |

The sandbox does not give these protections:

- **Network isolation by the CNI.** Flannel does not enforce NetworkPolicy. Learner code can send UDP to any address, DNS included. With Landlock ABI 4 or later, TCP reaches only ephemeral ports. With a lower ABI, or without Landlock, learner code can connect to each Service in the cluster. It can also connect to the home network and to the internet.
- **Isolation from the runner process without Landlock.** Learner code runs as the same user in the same container. If the `sandbox for runs` line is a WARN, learner code can read the runner token from `/proc`. It can also send a signal to the runner. It can also read the files of a concurrent run. With Landlock below ABI 6, it can still send a signal to the runner and `tini`. That restarts the pod.
- **A clean build cache.** Learner code can write to `/cache`. A changed cache entry can change the result of a later run of another learner. A new pod starts with a new cache from the image.
- **A kernel boundary.** The pod shares the kernel of the node. A kernel exploit leaves the sandbox. There is no gVisor and no Kata.
- **A hard disk quota.** The kubelet measures `/tmp` and `/cache` at intervals. A fast writer can go past the `sizeLimit` for some seconds before the eviction.
- **A limit on processes for each run.** The pod spec cannot set one. The kubelet limits each pod to 4096 PIDs (`podPidsLimit`, an Omni config patch since 2026-10-21, see `docs/tech/README.md`). A fork bomb in a run can use up the PIDs of the runner pod, not of the node, until the runner kills the run after 40 s. Until then, the other run in the pod fails.

### How to find out if the CNI enforces NetworkPolicy

1. List the DaemonSets in all namespaces:

   ```sh
   kubectl --context yornik-sharkshere get daemonsets -A
   ```

2. Call the runner from a pod in another namespace:

   ```sh
   kubectl --context yornik-sharkshere -n default run np-test --rm -it --restart=Never --image=alpine:3.24 -- \
     wget -qO- -T 5 http://runner.go-practice-runner.svc.cluster.local:8081/healthz
   ```

3. Record the result in `docs/tech/README.md`.

Expected result with enforcement: step 1 shows `cilium` or `calico-node`, and `wget` in step 2 times out. If step 1 shows only `kube-flannel` and step 2 gets an answer, the CNI does not enforce NetworkPolicy.

NOTE: On 2026-10-17, step 1 showed only `kube-flannel` (`ghcr.io/siderolabs/flannel:v0.28.4`), and the cluster had no CRD of Cilium, Calico or kube-router. The CNI does not enforce NetworkPolicy. Do the check again after a change of the CNI.

WARNING: If the CNI does not enforce NetworkPolicy, Landlock is the only network control. With Landlock ABI 4 or later, learner code connects over TCP only to ephemeral ports. It can still send UDP to any address. Without Landlock, or below ABI 4, learner code has the network access of an ordinary pod. Then invite only people that you trust.

## If the site has no valid certificate

The cause is a failed ACME order. Examples are a name that did not resolve yet, or a challenge path that did not reach Traefik.

Traefik v3.7.4 does not try a failed order again on a timer. It tries again each time its dynamic configuration changes, for example when a route, or a pod behind a route, changes anywhere in the cluster. While the cause stays, each of these tries fails too. After the fix, the next change can get the certificate without a restart.

CAUTION: A restart of Traefik stops every public domain for some seconds. The Deployment has `maxSurge: 0`.

NOTE: Let's Encrypt refuses new orders for a host for 1 hour after 5 failed validations. The tries that Traefik starts by itself count too. Fix the cause first, and do not restart Traefik again and again.

1. Make sure that the name resolves. For `vesper-labs.org`, see [step 2](#2-merge-the-dns-change) of the move. For `go-learn.party`, see [step 3](#3-publish-the-dns-record-before-the-route) of the first deploy.
2. Make sure that the challenge path reaches Traefik. Use the command of step 2 in [Before the certificate change](#before-the-certificate-change). For `go-learn.party`, put that name in the URL.
3. Read the certificate of the name. Replace `<host>` with the name:

   ```sh
   echo | openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -text | grep -e 'Issuer:' -e 'DNS:'
   ```

   If you get an issuer with `O=Let's Encrypt` and `DNS:<host>`, a later try got the certificate. Do not restart Traefik, and skip steps 4 to 6.

4. Restart Traefik:

   ```sh
   kubectl --context yornik-sharkshere -n traefik rollout restart deploy/traefik
   ```

5. Wait for the rollout:

   ```sh
   kubectl --context yornik-sharkshere -n traefik rollout status deploy/traefik
   ```

6. Read the headers of the site:

   ```sh
   curl -sSI https://vesper-labs.org/ | grep -i '^HTTP'
   ```

Expected result: a `200` with no certificate error.

NOTE: For the certificate of `go-learn.party`, read the headers of `https://go-learn.party/` instead. The expected result is then a `308` to `https://vesper-labs.org/`: `curl -I` sends HEAD, and Traefik answers 308 to each method except GET.

## Problems

| Symptom | Cause | Correction |
|---|---|---|
| A pod reports `ImagePullBackOff` with `unauthorized` or `denied`. | The GHCR package is private. | Do [step 1](#1-release-the-images) of the first deploy. |
| The web pod is in `CrashLoopBackOff`, and the log shows `web server stopped` with `unable to open database file` for `/data/go-practice.db`. | UID 65532 cannot write to the NFS dataset. The CSI driver did not apply `fsGroup`. | Read the mode of the dataset on TrueNAS. Make the dataset writable for UID 65532 or group 65532. |
| The IDE reports that the runner is down, and the web log shows 401 from the runner. | The 2 Secrets hold different tokens, or 1 pod still has the old token. | Do [How to rotate the runner token](#how-to-rotate-the-runner-token). It writes 1 new value to both Secrets and restarts both pods, and nobody has to print a token. |
| The runner pod restarts with `OOMKilled`. | A test allocated past 5 GiB, or 2 race builds and a test came together. | No action for 1 event. If it repeats, read `container_memory_working_set_bytes` and the runner metrics before a change of the limit. |
| The runner pod is `Evicted`. | `/tmp` or `/cache` went past its `sizeLimit`. | No action for 1 event. The Deployment starts a new pod. If it repeats, find the run in the runner log. If the kubelet evicts the pod every few days, the build cache in `/cache` grows faster than Go removes old entries. Read the comment on the volume in `deployment-runner.yaml`. |
| The runner log shows `race detector not available: test runs go without -race`, and the IDE says that the race detector is not available. | The race probe at start failed on this node. The `reason` field of the log line gives the error. `FATAL: ThreadSanitizer` points to the seccomp profile `RuntimeDefault`, which can block `personality(ADDR_NO_RANDOMIZE)`. | Tests still run without `-race`. A learner can then pass an exercise without `-race`. Read the `reason` field: `kubectl --context yornik-sharkshere -n go-practice-runner logs deploy/go-practice-runner \| grep 'race detector'`. Each new pod tests again, so a pod on another node can have a race detector. A `Localhost` seccomp profile that is `RuntimeDefault` plus `personality(ADDR_NO_RANDOMIZE)` brings `-race` back. Do not change the seccomp profile without a review of the sandbox. |
| The runner log shows a WARN `sandbox for runs` line, or a `landlock ABI` below 6. | The node kernel does not have Landlock in its active LSM list, or is older than Linux 6.12. | Without Landlock, runs are not confined. Then invite only people that you trust. For what each ABI gives, read [What the runner sandbox does and does not do](#what-the-runner-sandbox-does-and-does-not-do). The fix is a node kernel with Landlock, through a Talos upgrade. |
| The job `caa-updater-go-learn` or `caa-updater-vesper` fails with `CAA drift`. | Universal SSL is on for the zone. | Do steps 6 and 7 of [step 2](#2-prepare-the-cloudflare-zone) for that zone. |
| The job `dane-updater-vesper` fails with `it served no certificate`. | `vesper-labs.org` served no certificate at the time of the run, because its ACME order failed. The job did not change the TLSA record. | Do [If the site has no valid certificate](#if-the-site-has-no-valid-certificate). The next run at 03:43 UTC sets the record. |
| A learner reports that the passkey does not work, and the browser offers no passkey for the site. | The passkey was made on `go-learn.party`. It works only on that host. | The learner selects "Recover your account" on `https://vesper-labs.org/login`. The recovery adds a new passkey. |
| Mail does not arrive, and the log shows the mail text. | `GPW_SMTP_PASSWORD` is still `REPLACE_ME`. | Do [How to set the Resend API key](#how-to-set-the-resend-api-key). |
| Mail does not arrive, and the web log shows an error with `auth:` in its `err` field. | Resend refuses the key. Somebody rotated or revoked the key of soiree, and the copy in `secret-web.enc.yaml` is the old key. | Copy the key again: do [How to set the Resend API key](#how-to-set-the-resend-api-key). |
| Mail does not arrive after the move, and the web log shows an SMTP error without `auth:`. | Resend refuses the sender. `vesper-labs.org` is not Verified in Resend, or the key cannot send from that domain. | In Resend, open Domains, then API Keys. Do steps 5 to 7 of [Before the merge](#before-the-merge). |
| The mail arrives in the spam folder. | `vesper-labs.org` is a new domain, and a filter does not trust it yet. SPF, DKIM and DMARC can all pass. | Tell the learners to look in the spam folder. Mark the mail as not spam. The domain gets a reputation over some weeks. |
