# sharkshere-gitops

GitOps workload control plane for the sharkshere Kubernetes platform.

This repo is the application/policy layer in a 3-repo architecture:

1. `jumpingsharks`: provisions edge infrastructure and DNS/rDNS
2. `sharkshere-ansible`: hardens/configures edge hosts
3. `sharkshere-gitops` (this repo): reconciles cluster workloads and runtime policy

## Cluster Profile

| Item | Value |
|------|-------|
| Nodes | 4x Intel N150 |
| Topology | 3 control-plane + 1 worker (all schedulable) |
| Memory | 32 GB per node |
| Storage | ~475 GB per node |
| OS | Talos Linux |
| GPU | Intel iGPU on all nodes |

## Repository Layout

```text
apps/           app-of-apps chart producing Argo CD Applications
bootstrap/      Argo CD bootstrap manifests
manifests/      per-app manifests and Kustomize overlays
```

## Reconciliation Model

1. Bootstrap installs Argo CD and root app.
2. Root app renders one `Application` per entry in `apps/values.yaml`.
3. Argo CD continuously enforces desired state (prune + self-heal).
4. **GitHub webhook** → `https://argocd.fedishark.eu/api/webhook` triggers an immediate sync on every push to `main`, so ArgoCD reconciles within seconds of a merge rather than waiting for the default 3-minute polling interval. Configured under the repo's GitHub Settings → Webhooks.

## Application Inventory

### Local manifests

| App | Namespace | Purpose |
|-----|-----------|---------|
| `local-path-provisioner` | `local-path-storage` | node-local default storage class |
| `external-dns` | `external-dns` | DNS automation for `fedishark.eu` + `yornik.eu` |
| `monitoring` | `monitoring` | monitoring namespace, ingress, secrets |
| `tibber-exporter` | `monitoring` | energy metrics exporter |
| `gotosocial` | `gotosocial` | fediverse service (`pub.fedishark.eu`) |
| `jellyfin` | `jellyfin` | media service (`jelly.yornik.eu`) |
| `omni-tools` | `omni-tools` | utility services |
| `qbittorrent` | `jellyfin` | torrent workload |
| `democratic-csi` | `democratic-csi` | CSI config bootstrap |
| `muse` | `muse` | app workload |
| `argocd-config` | `argocd` | ArgoCD IngressRoute + fail2ban middleware |
| `vaultwarden` | `vaultwarden` | password manager (`passwords.yornik.eu`) |
| `vikunja` | `vikunja` | task management (`todo.yornik.eu`) |
| `asf` | `asf` | app workload |
| `fedishark` | `fedishark` | public landing site |
| `yornik` | `yornik` | professional site (`yornik.eu`) |
| `privatebin` | `privatebin` | secure paste service (`secrets.yornik.eu`) |
| `traefik-config` | `traefik` | shared edge middleware and `security.txt` |
| `tailscale` | `tailscale` | cluster-side tailscale resources |
| `shared-pg` | `shared-pg` | multi-tenant CNPG Postgres Cluster (3-instance HA, WAL archive to Hetzner OS) — hosts app databases that don't need their own dedicated cluster |

### Helm apps

| App | Namespace | Chart |
|-----|-----------|-------|
| `smb-csi-driver` | `kube-system` | `csi-driver-smb` |
| `kube-prometheus-stack` | `monitoring` | `kube-prometheus-stack` |
| `loki` | `monitoring` | `loki` |
| `alloy` | `monitoring` | `alloy` |
| `democratic-csi-nfs` | `democratic-csi` | `democratic-csi` |
| `democratic-csi-nfs-ssd` | `democratic-csi` | `democratic-csi` |
| `democratic-csi-iscsi` | `democratic-csi` | `democratic-csi` |
| `democratic-csi-iscsi-ssd` | `democratic-csi` | `democratic-csi` |
| `traefik` | `traefik` | `traefik` |
| `tailscale-operator` | `tailscale` | `tailscale-operator` |
| `cnpg-operator` | `cnpg-system` | `cloudnative-pg` |
| `cnpg-plugin-barman-cloud` | `cnpg-system` | `plugin-barman-cloud` |
| `cert-manager` | `cert-manager` | `cert-manager` |

## Storage Classes

| StorageClass | Protocol | Backing pool | Notes |
|--------------|----------|--------------|-------|
| `truenas-nfs` (default) | NFS | `Big_Pool` raidz1 (7× HDD) | Jellyfin media, GoToSocial storage, Vikunja files — bulk/sequential IO only |
| `truenas-ssd` | NFS | `ssd_pool` mirror (2× Samsung 870 EVO 1 TB) | App PVCs — config, attachments, small state (dataset `sync=disabled`, fast but RAM-buffered) |
| `truenas-ssd-iscsi` | iSCSI | `ssd_pool` mirror | CNPG Postgres Clusters — ext4 on zvol with `sync=standard` for real per-commit durability |
| `truenas-iscsi` | iSCSI | `Big_Pool` | Block storage (HDD-backed, rarely used) |
| `smb` | SMB | `Big_Pool/Share` | Jellyfin media read-only |
| `smb-rw` | SMB | `Big_Pool/Share` | qBittorrent downloads read-write |
| `local-path` | hostPath | Node-local | Jellyfin config (node-pinned) |

## Engineering Signals

- Git-driven reconciliation as the source of truth.
- Split between local manifests and chart-managed components where appropriate.
- Centralized logging pipeline (`Alloy -> Loki`) with noise filtering at ingestion.
- Shared edge hardening (`CSP`, selective `no-compression`, centralized `security.txt`).
- Explicit sender-domain alignment for app mailers (`@yornik.eu`).
- Registration controls for public apps (`Vikunja` registration disabled).

## Homelab Constraints

Known single points of failure in this environment:

- Single residential power feed
- Single residential internet uplink
- Shared NAS-backed storage dependency for part of the stateful workload set

These risks are intentional tradeoffs for a homelab budget/complexity envelope. Full mitigation (dual power path, dual WAN with proper edge failover, fully independent replicated storage domains) is possible, but currently disproportionate in cost and operational overhead for this environment.

## Domain and Edge Notes

- ExternalDNS manages subdomains for `fedishark.eu` and `yornik.eu`.
- Apex records for both `yornik.eu` and `fedishark.eu` are managed by ExternalDNS via dummy Services in `manifests/external-dns/dns-records.yaml`, pointing directly at the jump host IPs (Cloudflare doesn't support CNAME flattening conflicts with DANE TLSA).
- `www.yornik.eu` redirects to apex.
- Shared edge policy lives in `manifests/traefik-config/`.
- DNSSEC/DANE (TLSA) is applied selectively where it provides practical value and manageable operational overhead, rather than blanket-enabling it for every endpoint.

## Bootstrap

Prerequisite: `kubectl` context with cluster access.

```sh
kubectl apply -f bootstrap/argocd-namespace.yaml
kubectl apply -f bootstrap/argocd-install.yaml
kubectl apply -f bootstrap/argocd-project.yaml
kubectl apply -f bootstrap/root-app.yaml
```

## Secrets

Secrets are encrypted with SOPS (`*.enc.yaml`) and decrypted during sync via KSOPS.

## CI

PR checks:

1. YAML lint
2. Helm template
3. Kubeconform (raw manifests)
4. Kubeconform on rendered Helm output

## Dependency Updates

Renovate is enabled. Patch/minor image updates are auto-merged; major bumps require review.
