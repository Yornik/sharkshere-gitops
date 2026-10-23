# ArgoCD does not apply an EndpointSlice from git

**Date:** 2026-10-23
**Component:** `argocd` (`resource.exclusions`), `truenas-ui` and `truenas-smb` Applications
**Severity:** none. A design fault found before the merge

## Effect

The first design for the TrueNAS web interface on the tailnet was a Service without a selector, plus an `EndpointSlice` that names `192.168.1.42`. ArgoCD would have created the Service and skipped the `EndpointSlice`. The Service would have had no endpoints. The page would not load, and the Application would have shown a warning, not an error.

## Cause

ArgoCD excludes some kinds from its view of the cluster. The upstream `argocd-cm` that `bootstrap/argocd/install.yaml` ships lists `Endpoints` and `discovery.k8s.io/EndpointSlice` in `resource.exclusions`. `bootstrap/argocd/argocd-cm-patch.yaml` does not change that list.

When ArgoCD compares an Application, it removes each manifest from git that has an excluded kind. It then adds the condition `ExcludedResourceWarning` with the message `Resource <group>/<kind> <name> is excluded in the settings`. It does not apply the manifest.

The Tailscale operator adds a second limit. A backend Service of a Tailscale Ingress must have a ClusterIP, and the operator builds the proxy target from it. A Service of type `ExternalName` and a headless Service have none, so the operator refuses both with the event `InvalidIngressBackend`.

## Correction

Put a pod in front of the NAS. The `truenas-ui` Application runs an nginx pod that relays TCP to `192.168.1.42:443`. A Service with a selector fronts the pod. The cluster creates the endpoints of that Service itself, so git holds no `EndpointSlice`.

## Prevention

1. Do not put an `Endpoints` or an `EndpointSlice` in `manifests/`. ArgoCD drops it.
2. Do not use an `ExternalName` Service as the backend of a Tailscale Ingress.
3. After a sync, read the Application conditions. A warning that names an excluded kind means that ArgoCD skipped a manifest.

To manage an excluded kind from git, remove it from `resource.exclusions` in `bootstrap/argocd/argocd-cm-patch.yaml`. That change needs the manual bootstrap apply in [`AGENTS.md`](../../AGENTS.md), and ArgoCD then watches every `EndpointSlice` in the cluster. The exclusion exists to reduce that load. The relay pod costs less.

## Evidence

- `bootstrap/argocd/install.yaml`, the `resource.exclusions` key of `argocd-cm`.
- ArgoCD v3.5.6, `controller/state.go`, the loop that calls `IsExcludedResource` and appends `ApplicationConditionExcludedResourceWarning`.
- Tailscale operator v1.104.1, `cmd/k8s-operator/ingress.go`, the check on `svc.Spec.ClusterIP`, and the choice of `https+insecure://` for port 443.
- `manifests/truenas-ui/` and `manifests/truenas-smb/`, the relays that replace the `EndpointSlice`.
