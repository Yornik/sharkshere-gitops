# sharkshere-gitops

This repository holds the desired state of the sharkshere Kubernetes cluster. ArgoCD reads this repository and makes the cluster agree with it.

## What this repository does

- It defines about 40 ArgoCD Applications for a 4-node Talos Linux cluster.
- It serves 14 public HTTPS domains. Examples are GitLab CE, OpenProject, Vaultwarden, Jellyfin and a Fediverse instance.
- It keeps all secrets encrypted with SOPS and age. ArgoCD decrypts them in the cluster with KSOPS.

This repository is one of three:

| Repository | Layer | Function |
|---|---|---|
| [`jumpingsharks`](https://github.com/Yornik/jumpingsharks) | infrastructure | Creates the two Hetzner edge hosts and their DNS with OpenTofu. |
| [`sharkshere-ansible`](https://github.com/Yornik/sharkshere-ansible) | hosts | Hardens the edge hosts. Installs HAProxy, Tailscale and fail2ban. |
| `sharkshere-gitops` (this repository) | workloads | Reconciles the applications in the cluster with ArgoCD. |

## Documents

| Document | Content |
|---|---|
| [`docs/tech/README.md`](docs/tech/README.md) | Full technical overview: traffic flow, storage classes, application inventory, public domains, constraints. |
| [`docs/styleguide.md`](docs/styleguide.md) | Writing rules for this README, the files in `docs/` and manifest comments. |
| [`docs/incidents/`](docs/incidents/README.md) | One write-up for each incident or significant finding. Each has a cause, a correction and a prevention. |

## Repository layout

```text
apps/           Helm chart. It renders one ArgoCD Application for each entry in apps/values.yaml.
bootstrap/      Manifests that install ArgoCD and the root Application on an empty cluster.
manifests/      Plain manifests and Kustomize overlays, one directory for each application.
docs/           Technical overview, style guide and incident write-ups.
```

## How a change reaches the cluster

1. Open a pull request against `main`.
2. CI runs seven checks. See [CI checks](#ci-checks).
3. Merge the pull request.
4. GitHub sends a webhook to ArgoCD.
5. ArgoCD syncs the root Application within seconds.
6. ArgoCD removes resources that are not in git. ArgoCD reverts changes made by hand.

CAUTION: Do not change resources on the cluster by hand. ArgoCD reverts the change on the next sync. Put the change in git.

NOTE: Some corrections need one action on the cluster that git cannot express. Record each such action in `docs/incidents/`.

## How to add an application

1. Add an entry under `apps:` in `apps/values.yaml`.
2. For a Helm chart, give `helm.repoURL`, `helm.chart`, `helm.targetRevision` and `helm.values`.
3. For plain manifests, give `path` and put the manifests in `manifests/<name>/`.
4. If the chart uses a new Helm repository, add the URL to `sourceRepos` in `bootstrap/argocd-project.yaml`. If you do not, ArgoCD reports `repository not permitted`.
5. Add a comment for each value that is not obvious. Give the reason, not the description.
6. Open a pull request.

## How to add a secret

1. Create the manifest with the plain secret.
2. Encrypt the file with `sops`. Name it `*.enc.yaml`.
3. Reference the file from a `ksops` generator in the Kustomization.
4. Commit only the encrypted file.

CAUTION: Do not commit a plain secret. The age private key is only in the ArgoCD repo-server.

## How to update a chart or an image

Renovate opens the pull request. Do not edit the version by hand.

1. Read the upstream change notes for the new version.
2. If the version crosses a major, read the upgrade guide of the chart.
3. Check that CI is green.
4. Merge the pull request.
5. Check the Application in ArgoCD. Make sure it reports Synced and Healthy.
6. If the Application does not become Healthy, read the Application conditions and the pod events first.

WARNING: A workload with one replica on a ReadWriteOnce volume must use the `Recreate` strategy or `maxSurge: 0`. If it does not, the update stops with a `Multi-Attach` or `FailedAttachVolume` event. See `docs/incidents/`.

## How to bootstrap an empty cluster

Prerequisite: a `kubectl` context with cluster access and the age key for SOPS.

```sh
kubectl apply -f bootstrap/argocd-namespace.yaml
kubectl apply --server-side --force-conflicts -k bootstrap/argocd/
sops -d bootstrap/argocd-secret.enc.yaml | kubectl apply -f -
kubectl apply -f bootstrap/argocd-project.yaml
kubectl apply -f bootstrap/root-app.yaml
```

After the last command, ArgoCD creates all other Applications from `apps/values.yaml`.

## CI checks

CI runs on each pull request. All seven checks must pass before a merge.

| Check | What it does |
|---|---|
| YAML Lint | Runs `yamllint` on `manifests/` and `bootstrap/`. |
| Validate security.txt | Checks the signature of the published `security.txt`. |
| Verify ksops pinned hash | Compares the embedded KSOPS checksum with the upstream release. |
| Helm Template Check | Renders the `apps/` chart. |
| Render Charts With Values | Renders each upstream chart with the exact values from `apps/values.yaml`. |
| Validate Kubernetes Schemas | Runs `kubeconform` with CRD schemas on the plain manifests and the bootstrap overlay. |
| Validate Rendered Helm Output | Runs `kubeconform` on the rendered Helm output. |

A full run takes about 20 seconds.

## Known limits

The cluster is in a home. It has one power feed, one internet uplink and one NAS for shared storage. These are accepted limits. See [`docs/tech/README.md`](docs/tech/README.md#homelab-constraints) for the reasons.
