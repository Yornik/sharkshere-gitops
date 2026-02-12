# sharkshere-gitops

GitOps repository for the **sharkshere** Kubernetes cluster — a 4-node Talos Linux cluster managed via Sidero Omni. Argo CD bootstraps itself and deploys all workloads through an app-of-apps Helm chart.

## Cluster

| Nodes | CPU | RAM | Storage | OS |
|-------|-----|-----|---------|----|
| 4x Intel N150 | 4 cores each | 32 GB each | ~475 GB each | Talos Linux |

3 control-plane nodes (scheduling enabled) + 1 worker. All 4 nodes accept workloads and each has an Intel iGPU available for hardware transcoding.

## Repository Layout

```
apps/           Helm chart that renders Argo CD Application resources (app-of-apps)
bootstrap/      Manifests to install Argo CD and seed the root application
manifests/      Per-application manifests and Kustomize overlays
```

## Deployed Applications

| Application | Namespace | Source | Description |
|-------------|-----------|--------|-------------|
| **example-app** | `example` | Local manifests | Nginx demo deployment |
| **local-path-provisioner** | `local-path-storage` | Local manifests | Default StorageClass using node-local storage |
| **smb-csi-driver** | `kube-system` | Helm chart | CSI driver for mounting SMB/CIFS shares |
| **external-dns** | `external-dns` | Local manifests | deSEC DNS webhook for `fedishark.eu` |
| **monitoring** | `monitoring` | Local manifests | Namespace, Grafana ingress, and SOPS secrets |
| **kube-prometheus-stack** | `monitoring` | Helm chart | Prometheus, Grafana, Alertmanager, node-exporter, kube-state-metrics |
| **loki** | `monitoring` | Helm chart | Log storage backend for Grafana Explore |
| **alloy** | `monitoring` | Helm chart | Log and metrics agent (DaemonSet), shipping Kubernetes logs to Loki |
| **tibber-exporter** | `monitoring` | Local manifests | Tibber power metrics exporter with Grafana dashboard |
| **jellyfin** | `jellyfin` | Local manifests | Media server with VAAPI transcoding and SMB-backed storage |
| **gotosocial** | `gotosocial` | Local manifests | Federated social server published at `pub.fedishark.eu` |

All applications use automated sync with prune and self-heal enabled.

## How It Works

1. Bootstrap manifests install Argo CD and create the root application.
2. The root application points at `apps/` and renders one `Application` per entry in `apps/values.yaml`.
3. Argo CD continuously syncs each application from this repo or from external Helm charts.

## Bootstrap

Prerequisites: `kubectl` with cluster access.

```sh
kubectl apply -f bootstrap/argocd-namespace.yaml
kubectl apply -f bootstrap/argocd-install.yaml
kubectl apply -f bootstrap/argocd-project.yaml
kubectl apply -f bootstrap/root-app.yaml
```

After the root application is created, Argo CD takes over and deploys everything else.

## Managing Apps

Edit `apps/values.yaml` to add or remove applications.

- **Local manifests:** add an entry with `path: manifests/<app>` and commit manifests under that directory.
- **Helm charts:** add an entry under `apps.<name>.helm` with `repoURL`, `chart`, and `targetRevision`.

## Tibber Notes

- `tibber-exporter` metrics are scraped by Prometheus via `ServiceMonitor` in `manifests/tibber-exporter/servicemonitor.yaml`.
- Dashboard panels use Grafana datasource variable `$datasource` (not hardcoded datasource UID).
- Cost and consumption panels are configured for 15-minute buckets using Prometheus `increase(...[15m])`.
- If you build a quarter-hour Tibber exporter fork, update `manifests/tibber-exporter/deployment.yaml` image to your fork tag and keep the same metric names for dashboard compatibility.

## Secrets

Secrets are encrypted with [SOPS](https://github.com/getsops/sops) using age encryption. Encrypted files follow the `*.enc.yaml` naming convention.

At sync time, Argo CD decrypts secrets via [KSOPS](https://github.com/viaductoss/ksops) generators (`secret-generator.yaml` in each app that needs secrets).

## CI

Every pull request runs four checks:

1. **YAML lint** — validates manifests and bootstrap files
2. **Helm template** — renders the app-of-apps chart
3. **Kubeconform** — schema validation on raw manifests
4. **Helm + Kubeconform** — schema validation on rendered Helm output

## Dependency Updates

[Renovate](https://docs.renovatebot.com/) monitors this repo for dependency updates. Patch and minor container image updates are auto-merged; major updates and Helm chart bumps require manual review.
