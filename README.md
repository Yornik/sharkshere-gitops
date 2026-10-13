# sharkshere-gitops

This repository holds the desired state of the sharkshere Kubernetes cluster. ArgoCD reads this repository and makes the cluster agree with it.

## What this repository does

- It defines about 40 ArgoCD Applications for a 4-node Talos Linux cluster.
- It serves 13 public HTTPS domains. Examples are GitLab CE, OpenProject, Vaultwarden, Jellyfin and a Fediverse instance.
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
| [`AGENTS.md`](AGENTS.md) | Instructions for a coding agent. `CLAUDE.md` points here. |
| [`REVIEW.md`](REVIEW.md) | 2 checklists for a pull request: A for a dependency bump, B for a change. The `Claude review` CI job uses them. |
| [`docs/styleguide.md`](docs/styleguide.md) | Writing rules for this README, the files in `docs/` and manifest comments. |
| [`docs/incidents/`](docs/incidents/README.md) | One write-up for each incident or significant finding. Each has a cause, a correction and a prevention. |
| [`docs/runbooks/`](docs/runbooks/) | Procedures for one application each: how to activate, check, restore or repair it. |

## Repository layout

```text
apps/           Helm chart. It renders one ArgoCD Application for each entry in apps/values.yaml.
bootstrap/      Manifests that install ArgoCD and the root Application on an empty cluster.
manifests/      Plain manifests and Kustomize overlays, one directory for each application.
docs/           Technical overview, style guide, runbooks and incident write-ups.
```

## How a change reaches the cluster

1. Open a pull request against `main`.
2. CI runs 8 checks. See [CI checks](#ci-checks).
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

CI runs on each pull request. All 8 checks must pass before a merge.

| Check | What it does |
|---|---|
| YAML Lint | Runs `yamllint` on `manifests/` and `bootstrap/`. |
| Validate security.txt | Checks the signature of the published `security.txt`. |
| Verify ksops pinned hash | Compares the embedded KSOPS checksum with the upstream release. |
| Helm Template Check | Renders the `apps/` chart. |
| Render Charts With Values | Renders each upstream chart with the exact values from `apps/values.yaml`. |
| Validate Kubernetes Schemas | Runs `kubeconform` with CRD schemas on the plain manifests and the bootstrap overlay. |
| Validate Rendered Helm Output | Runs `kubeconform` on the rendered Helm output. |
| Review tools | Runs the tests for the tool boundary in [`.github/scripts/review.py`](.github/scripts/review.py). |

The 8 checks run in parallel and take about 20 seconds.

2 more checks run on each pull request. Neither gates the merge.

| Check | What it does |
|---|---|
| Decide whether to review | Reads the push and decides if the review runs. |
| Claude review | Reviews the pull request against [`REVIEW.md`](REVIEW.md) and posts 1 comment with a verdict. |

The Claude review runs on the Claude API, through [`.github/scripts/review.py`](.github/scripts/review.py). It needs the repository secret `ANTHROPIC_API_KEY`. Without the secret the check fails and the merge still works. The check reads the author to choose the checklist: a Renovate bump gets checklist A, any other author gets checklist B. It skips a draft. It skips a bump that carries the `automerge` label from `renovate.json5`, unless that bump also carries `helm`, `major` or `manual-apply`. It also skips a push that changes Markdown only, unless that Markdown sets the rules of the review. See the table in [`REVIEW.md`](REVIEW.md) and the job in [`.github/workflows/claude-review.yml`](.github/workflows/claude-review.yml).

NOTE: The verdict is advice. A person merges the pull request. A red check means that the review did not run, not that the change is bad.

## Known limits

The cluster is in a home. It has one power feed, one internet uplink and one NAS for shared storage. These are accepted limits. See [`docs/tech/README.md`](docs/tech/README.md#homelab-constraints) for the reasons.
