# Instructions for an agent

This file tells a coding agent how to work in this repository. It applies to Claude Code, to the `Review Renovate PR` CI job and to any other agent. A person reads [`README.md`](README.md) first.

ArgoCD reads this repository and makes the cluster agree with it. A change that merges to `main` reaches the cluster within seconds. Treat every change as a change to a running system.

## Documents

| Document | Read it when |
|---|---|
| [`README.md`](README.md) | You need the layout, the CI checks or a procedure. |
| [`docs/tech/README.md`](docs/tech/README.md) | You need the traffic flow, the storage classes or the application inventory. |
| [`REVIEW.md`](REVIEW.md) | You review a dependency pull request. |
| [`docs/styleguide.md`](docs/styleguide.md) | You write or edit a document, a README or a comment. |
| [`docs/incidents/`](docs/incidents/README.md) | You touch a component. Read the write-up for that component first. |

## Rules

1. Put every change in a pull request against `main`. Do not commit to `main`.
2. Do not change a resource on the cluster by hand. ArgoCD reverts the change on the next sync. Put the change in git.
3. Do not write a plaintext secret to a tracked file. Encrypt the file with `sops` and name it `*.enc.yaml`.
4. Do not weaken a CI check to make a pull request green. Fix the cause.
5. Add a comment for each value that is not obvious. Give the reason, not the description.
6. If a correction needs an action on the cluster that git cannot express, record the action in `docs/incidents/`.
7. Follow [`docs/styleguide.md`](docs/styleguide.md) for every document and every comment.

WARNING: `manifests/` and `apps/values.yaml` hold the desired state of 14 public HTTPS domains. A wrong selector or a wrong namespace takes a domain offline.

## How to validate a change

Run these commands before you open a pull request. They are the same checks that CI runs.

1. Render the app-of-apps chart:

```bash
helm template sharkshere-apps apps/ --namespace argocd
```

2. Render each upstream chart with the values it receives:

```bash
.github/scripts/validate-helm-values.sh
```

3. Lint the YAML:

```bash
yamllint -d '{extends: relaxed, rules: {line-length: {max: 200}}}' manifests/ bootstrap/
```

NOTE: Step 2 needs network access to each Helm repository. It is the check that catches a chart release that rejects the inline values.

## Where things live

```text
apps/values.yaml            One entry for each ArgoCD Application. Inline Helm values.
apps/templates/             The template that renders an Application from an entry.
manifests/<name>/           Plain manifests and Kustomize overlays.
bootstrap/                  ArgoCD itself and the root Application. ArgoCD does not manage this.
renovate.json5              Which bumps automerge, which need a person.
.github/workflows/          CI.
```

CAUTION: A change under `bootstrap/` does not reach the cluster on merge. It needs a `kubectl apply -k bootstrap/argocd/` by a person. A stale checkout on that apply rolls the cluster backwards. See [`docs/incidents/2026-09-17-stale-checkout-bootstrap-apply.md`](docs/incidents/2026-09-17-stale-checkout-bootstrap-apply.md).

## How to review a dependency pull request

Use [`REVIEW.md`](REVIEW.md). It holds the checklist and the verdicts.
