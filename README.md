# sharkshere-gitops

GitOps repo for the sharkshere Kubernetes cluster. Argo CD bootstraps itself and then deploys all cluster apps using an app-of-apps Helm chart.

## Layout

- `apps/`: Helm chart that renders Argo CD `Application` resources (app-of-apps).
- `bootstrap/`: Manifests to install Argo CD and seed the root application.
- `manifests/`: Per-application manifests or Kustomize overlays.

## How It Works

1. Apply the bootstrap manifests to install Argo CD and the root application.
2. The root application points at `apps/` and renders one `Application` per entry in `apps/values.yaml`.
3. Argo CD continuously syncs each application from this repo or external Helm charts.

## Bootstrap

Prereqs: `kubectl`, cluster access, and any Argo CD/KSOPS prerequisites you use in your environment.

1. Create the Argo CD namespace and install Argo CD:

```sh
kubectl apply -f bootstrap/argocd-namespace.yaml
kubectl apply -f bootstrap/argocd-install.yaml
kubectl apply -f bootstrap/argocd-project.yaml
```

2. Seed the root application:

```sh
kubectl apply -f bootstrap/root-app.yaml
```

## Managing Apps

Edit `apps/values.yaml` to add or remove applications.

Raw manifests or Kustomize: add an entry with `path: manifests/<app>` and commit manifests under `manifests/<app>/`.

Helm charts: add an entry under `apps.<name>.helm` with `repoURL`, `chart`, and `targetRevision`.

## Secrets

This repo uses KSOPS generators for encrypted secrets (see `secret-generator.yaml` in each app). Ensure your Argo CD setup includes KSOPS and SOPS decryption for `*.enc.yaml` files.

## Notes

- The default GitHub repo URL is set in `apps/values.yaml` and `bootstrap/root-app.yaml`.
- Argo CD applications are set to automated sync with prune and self-heal.
