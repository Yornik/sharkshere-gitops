# A stale checkout rolled ArgoCD and its Redis backwards

**Date:** 2026-09-17
**Component:** `bootstrap/argocd/` (ArgoCD itself, and its bundled `argocd-redis-ha` StatefulSet)
**Severity:** no user-facing outage. ArgoCD kept working. The cache lost its redundancy for about 20 minutes.

## Effect

ArgoCD ran v3.4.5 while `bootstrap/argocd/install.yaml` on `main` declared v3.5.3. The Redis StatefulSet ran `redis:8.8.1-alpine` while the same file declared `8.10.1-alpine`.

One cache replica, `argocd-redis-ha-server-2`, could not start. It restarted 8 times with this error:

```
Redis version=8.8.1
# Can't handle RDB format version 15
# Fatal error loading the DB, check server logs. Exiting.
```

Every ArgoCD Application reported Synced and Healthy for the whole period. The ArgoCD UI and API stayed available. Nothing raised an alert.

## Cause

ArgoCD does not manage its own bootstrap manifest, so a merge to `bootstrap/` needs an operator to run `kubectl apply`. Pull request #463 carries the `manual-apply` label for that reason.

The apply ran from a local clone that was behind `main`. The clone predated commit `a0ab0ff`, which had raised ArgoCD from v3.4.5 to v3.5.2. The apply therefore wrote v3.4.5 over a cluster already running v3.5.2, and wrote `redis:8.8.1-alpine` over `8.10.1-alpine`. A manual apply declares the whole overlay, so an old checkout is a downgrade, not a no-op.

The Redis failure follows from the downgrade. The persisted RDB file on that volume was written by the newer Redis. Version 8.8.1 cannot read RDB format version 15, so it exits.

NOTE: The StatefulSet uses `podManagementPolicy: OrderedReady`, which updates pods in descending ordinal order and waits for each one to become Ready. The bad rollout reached pod 2, stalled there, and never touched pods 1 and 0. That accident is the only reason the cache kept quorum. Two of three replicas stayed on the correct version.

## Correction

Two steps were needed. The first was not enough.

1. Update the clone and apply again:

```sh
git checkout main && git pull
kubectl --context yornik-sharkshere apply --server-side --force-conflicts -k bootstrap/argocd/
```

This brought ArgoCD to v3.5.3 and set the StatefulSet image back to `8.10.1-alpine`. The ArgoCD Deployments rolled normally.

2. The StatefulSet did not replace pod 2. `OrderedReady` does not perform updates while a pod is not Ready, and the pod that needed replacing was the pod that was not Ready. Delete it by hand:

```sh
kubectl --context yornik-sharkshere -n argocd delete pod argocd-redis-ha-server-2
```

The pod came back on the current revision with `8.10.1-alpine` in 70 seconds, 3/3 Ready, 0 restarts. The StatefulSet then reported 3/3.

## Prevention

- Before a manual apply, make sure the clone is current. Run `git fetch` and confirm the branch is not behind.
- Read the image tags in the diff you are about to apply. A manual apply of `bootstrap/` can move a version in either direction.
- After the apply, compare the running version against git. Do not rely on Application health, which stays green through a bootstrap downgrade:

```sh
kubectl -n argocd get deploy argocd-server \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
grep -o 'quay.io/argoproj/argocd:v[0-9.]*' bootstrap/argocd/install.yaml | sort -u
```

WARNING: A `redis-ha` pod that will not start is not cosmetic. Quorum is 2 of 3. With one replica down, the loss of one more node takes the ArgoCD cache with it.

CAUTION: The ArgoCD API reports the version of whichever pod serves the request. During a rollout it can report the old version while new pods are already Ready. Check the pod images, not only `/api/version`.

## Evidence

- Pull request #463 merged at 18:42:49. The `kubectl / Apply` entry in `managedFields` on `argocd-server` is stamped 18:43:38. All ArgoCD pods were recreated at 18:43:49.
- `git log -S 'quay.io/argoproj/argocd:v3.4.5' -- bootstrap/argocd/install.yaml` shows v3.4.5 only in commits before `a0ab0ff`, which is what identified the checkout as stale.
- `bootstrap/argocd/kustomization.yaml` has no image transformer, so the tag came from `install.yaml` itself and not from an overlay override.
