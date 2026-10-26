# A Redis bump merged to `bootstrap/` with no sign that it needs a manual apply

**Date:** 2026-10-26
**Component:** `renovate.json5`, `bootstrap/argocd/install.yaml` (the `argocd-redis-ha-server` StatefulSet)
**Severity:** near miss. No outage. The cluster ran an older image than `main` declared until an operator applied `bootstrap/` by hand.

## Effect

Renovate opened pull request #603 at 17:00 UTC. It raised Redis in `bootstrap/argocd/install.yaml` from `8.10.2-alpine` to `8.10.3-alpine`, on 4 image lines.

The pull request carried the labels `automerge`, `dependencies` and `renovate`. Its body said "Automerge: Enabled". It held no warning and no apply command.

An operator merged it at 17:34 UTC. ArgoCD does not manage `bootstrap/`, so the merge changed git and left the cluster on 8.10.2. Nothing in the pull request or in CI said so.

The operator noticed the gap and applied `bootstrap/` by hand.

Nothing failed. Every Application stays Synced and Healthy while `bootstrap/` and the cluster disagree. No alert covers that gap.

## Cause

`renovate.json5` had a rule for `quay.io/argoproj/argocd` and a rule for `viaduct-ai/kustomize-sops`. Each sets `automerge: false`, the labels `bootstrap` and `manual-apply`, and a `prBodyNotes` warning with the apply command. No other package under `bootstrap/` had a rule.

The `kubernetes` manager reads `bootstrap/argocd/install.yaml` and `bootstrap/argocd/repo-server-ksops-patch.yaml`. Besides ArgoCD it finds 4 images: Redis, dex, haproxy and the `alpine` init container. Those fell to the generic rules. The patch rule and the docker minor rule set `automerge: true` and the `automerge` label, and they add no note.

The same bump in `manifests/` is correct under those rules, because ArgoCD applies `manifests/` within seconds. The rules do not look at the path. Redis, dex and haproxy sit in the same file as ArgoCD, and the pull request looks like any other patch bump.

Two safeguards did not catch it:

- The `automerge` label tells the review gate in `claude-review.yml` to skip the pull request. Check A7 of `REVIEW.md` asks for the apply command in the body, so it did not run.
- The review is off. The `Decide whether to review` and `Claude review` checks on #603 were both skipped. See the comment on the gate job.

This is not the first time. Renovate changed `install.yaml` for these images 6 times before #603. The label `manual-apply` first appears in `renovate.json5` on 2026-04-30 for ArgoCD and on 2026-07-11 for KSOPS. No rule covered these images at any of those times. See Evidence.

NOTE: The ArgoCD bumps themselves are covered. They carry `manual-apply` and the note, also when they ride in the patch group.

## Correction

1. Apply `bootstrap/` by hand from a current checkout:

```bash
git checkout main && git pull
kubectl --context yornik-sharkshere apply --server-side --force-conflicts -k bootstrap/argocd/
```

2. Add a rule to `renovate.json5` for every package in `bootstrap/**`, except the 2 that have their own rule. The rule sets `automerge: false`, `groupName: null`, the labels `bootstrap` and `manual-apply`, and a `prBodyNotes` block with the apply command and a check of the running images.

The new rule makes the review run, because the `manual-apply` label overrides the skip. It also keeps these images out of the patch group, so a sibling bump still merges itself.

A manual apply from a current checkout carries every earlier change in `install.yaml` as well. One apply therefore closes any other gap in that file. This write-up does not record the state of the cluster before the apply, so it cannot say if an earlier bump was pending.

CAUTION: A later rule adds its `prBodyNotes` to the notes of an earlier rule. The `!` patterns in the new rule keep the 2 packages that have their own rule from showing 2 notes.

## Prevention

- Make sure that a merge to `bootstrap/` is not a deploy. Treat the pull request as unfinished until the apply runs.
- The rule matches the path, so a new image under `bootstrap/` needs no new rule.
- After each apply, compare the running images with git:

```bash
kubectl --context yornik-sharkshere -n argocd get deploy,statefulset -o wide
grep -h 'image:' bootstrap/argocd/*.yaml | sort -u
```

- No alert covers the gap between `bootstrap/` and the cluster. A check that compares the running images in `argocd` with `install.yaml` would find it. It does not exist yet.

NOTE: The bump was a patch inside 8.10, the line that writes RDB format 15, so a rollback within the line reads the same files. A bump across a minor version needs check A5 of `REVIEW.md`. See [`2026-09-17-stale-checkout-bootstrap-apply.md`](2026-09-17-stale-checkout-bootstrap-apply.md).

WARNING: A stale checkout on the apply rolls the cluster backwards. Run `git pull` first.

## Evidence

- Pull request #603: labels `automerge`, `dependencies`, `renovate`. Merged by an operator at 2026-10-26 17:34:39 UTC. The body holds no apply command.
- The Renovate commit `dc39b15` changes 4 lines in `bootstrap/argocd/install.yaml`, all `redis:8.10.2-alpine` to `redis:8.10.3-alpine`.
- Earlier bumps of these images in `bootstrap/argocd/install.yaml` under the generic rules:

| Date | Commit | Change |
|---|---|---|
| 2026-09-21 | `f5c2657` | Redis `8.10.1-alpine` to `8.10.2-alpine` |
| 2026-09-25 | `ee97d2f` | haproxy `3.4.4-alpine` to `3.4.5-alpine` |
| 2026-09-29 | `f60bc66` | haproxy `3.4.5-alpine` to `3.4.6-alpine` |
| 2026-10-08 | `9ffed9f` | dex `v2.45.1` to `v2.46.0` |
| 2026-10-15 | `26617da` | haproxy `3.4.6-alpine` to `3.4.7-alpine` |
| 2026-10-23 | `c1023c1` | dex `v2.46.0` to `v2.46.1` |

- `git log -S"'manual-apply'" -- renovate.json5` lists commit `ae1d0c5` on 2026-04-30 (ArgoCD) and `0eee62f` on 2026-07-11 (KSOPS). No other package had the label.
- The images in `bootstrap/` before #603: `alpine:3.24`, `ghcr.io/dexidp/dex:v2.46.1`, `haproxy:3.4.7-alpine`, `redis:8.10.2-alpine` and `quay.io/argoproj/argocd:v3.5.6`.
- Renovate 44.184.1, run with the rules of the old and the new `renovate.json5` on the inputs of #603. The old rules give `automerge: true`, the group `patch updates`, the label `automerge` and no note. The new rules give `automerge: false`, no group, the labels `renovate`, `bootstrap` and `manual-apply`, and the note once. ArgoCD, KSOPS and the packages in `manifests/` give the same result under both.
