# The ArgoCD sync of the matrix app stalled on a wrong Traefik CRD group

**Date:** 2026-11-28
**Component:** `matrix` Application, Middleware `registration-ratelimit`, Traefik v3.7.4 CRDs
**Severity:** the OIDC switch from #741 did not reach the cluster for about 35 minutes. No data and no other Application were at risk. The homeserver kept serving.

## Effect

The merge of #741 (13:15:27 UTC) should have enabled the built-in OIDC server. Instead, the `matrix` Application sat `OutOfSync` while its auto-sync retried, and the Deployment kept the previous env. A client check made the gap visible:

```text
$ curl -s https://finfra.party/_matrix/client/v1/auth_metadata
{"errcode":"M_UNRECOGNIZED","error":"M_UNRECOGNIZED: OIDC server not configured"}
```

Element kept answering "Not supported by your account provider" on "Link new device". The webhook was not at fault: ArgoCD started the sync operation at 13:15:33 UTC, six seconds after the merge.

## Cause

The new Middleware `registration-ratelimit` shipped with the deprecated group:

```yaml
apiVersion: traefik.containo.us/v1alpha1
```

The cluster runs Traefik v3.7.4, which serves the renamed group `traefik.io/v1alpha1`. Every other Traefik object in this repository already uses it. The API server cannot discover the old group, so ArgoCD marked the whole sync invalid and entered a retry loop:

```text
failed to discover server resources for group version
traefik.containo.us/v1alpha1: the server could not find the requested
resource. Retrying attempt #5
```

One invalid resource blocks the apply of the whole manifest set, so the valid parts of #741 never landed either.

No CI check can catch this class of failure. Every schema validator skips Traefik CRD objects, because no published schema exists for them. The wrong group passed YAML lint and both schema checks.

## Correction

The stuck sync operation was cleared on the cluster:

```sh
kubectl -n argocd patch application matrix --type=json \
  -p '[{"op":"remove","path":"/operation"}]'
```

PR #742 changes the one line to `traefik.io/v1alpha1`. With the operation cleared and auto-sync on, the merge applies the whole of #741 with the corrected group.

## Prevention

1. Copy the `apiVersion` of a Traefik object from an existing house manifest, not from memory or upstream examples. The old `traefik.containo.us` group still appears in older documentation and posts.
2. When an Application sits `OutOfSync` with auto-sync on, read `status.operationState.message` first. The retry message names the exact group version that failed discovery.
3. A cheap guard can close the CI gap for Traefik objects: fail the pipeline when `grep -rn 'traefik.containo.us' manifests/` finds anything. The validators skip these CRDs, so a grep is the only check that sees the group.

## Evidence

- `kubectl -n argocd get application matrix -o json`: operation phase `Running` since 13:15:33 UTC, message quoted in Cause, sync revision `2d4c6f8`.
- `kubectl api-resources | grep traefik`: the served groups are `traefik.io` and `hub.traefik.io`; no `traefik.containo.us`.
- `grep -rh 'apiVersion: traefik' manifests/`: 18 objects, all `traefik.io/v1alpha1`, before this fix.
- `gh api repos/Yornik/sharkshere-gitops/hooks`: the GitHub webhook to `https://argocd.fedishark.eu/api/webhook` exists, and the six-second pickup above proves it delivered.
- The raw `auth_metadata` body above: the endpoint answers, so routing and Traefik worked; only the env var was missing.
