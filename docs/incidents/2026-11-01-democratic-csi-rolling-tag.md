# The storage driver ran the rolling tag `latest`, and no bot or review could see it

**Date:** 2026-11-01
**Component:** `democratic-csi`, `democratic-csi-nfs`, `democratic-csi-nfs-ssd`, `democratic-csi-iscsi`, `democratic-csi-iscsi-ssd` Applications
**Severity:** none yet. Found and corrected before any change of the image. The failure it allowed would have stopped all provisioning

## Effect

Nothing broke. The finding is a defect that was waiting.

All 20 driver containers of the 4 releases ran `ghcr.io/democratic-csi/democratic-csi:latest`, with `imagePullPolicy: Always`. Each restart of a pod pulled whatever `latest` pointed to at that moment. No git change, no pull request and no Renovate bump marked the change of that image.

The driver talks to the NAS. The NAS runs TrueNAS 25.10.7. On 2026-10-06 [the maintainer wrote](https://github.com/democratic-csi/democratic-csi/issues/509#issuecomment-6019619601) that the current `next` image supports TrueNAS 26 and later, and that support for all earlier versions "has been dropped entirely". Another homelab hit this on 25.10.7 when its chart used `next`. The driver reported `driver is only available with TrueNAS version >=26`, and no new volume could be provisioned (existing volumes kept working).

Here the same move of a tag would have stopped every new volume. That covers a CNPG replica, a restored PVC and each new app.

## Cause

The chart `democratic-csi` 0.15.1 sets the driver tag to `latest` for the controller and for the node. `apps/values.yaml` set no tag, so the chart default ran. Kubernetes pulls on every start for a `latest` tag.

Renovate tracked the chart version of the 4 releases. It did not track the image, because the image never appeared in git. A bare `latest` carries no version, so there is nothing for the bot to bump even when it sees the image.

The running `latest` was not `v1.9.5` either. The two digests differ. `latest` was built on 2026-01-07 at 23:13 UTC from commit `3974268`. `v1.9.5` was built the same day at 21:23 UTC from commit `b5be00c`. The 3 commits between them change one line of `README.md`. The code is the same, but nothing in git said so until someone compared the commits.

## Correction

1. The 4 releases pin the driver image to `v1.9.5` for the controller and for the node. `v1.9.5` is the last release that uses the REST API of TrueNAS 25.10.
2. A `# renovate:` comment sits above each `tag:`. A custom manager in `renovate.json5` reads the pair, so the bot sees the image.
3. A package rule turns automerge off for the driver image, and its pull request carries a note to check the TrueNAS version first. The rule near the top of `renovate.json5` would merge a docker minor bump by itself.

The pin changes no code. The README diff above shows that. Rolling the pods once pulls `v1.9.5` and runs the same driver.

## Prevention

1. No `latest`, `next`, `main` or untagged image in a workload. A tag names one build. A rolling tag names whatever the registry owner moves it to.
2. Do not trust the chart default for an image. Read the rendered output of the chart and look for the tag. A chart can ship `latest` as the default.
3. A storage driver and a NAS version move together. Before a bump of either, read the supported versions of the other.
4. Check the running cluster, not only git. This scan lists every container with a rolling tag:

```bash
kubectl --context yornik-sharkshere get pods -A -o json | python3 -c '
import sys,json
for p in json.load(sys.stdin)["items"]:
    for k in ("containers","initContainers"):
        for x in p["spec"].get(k,[]):
            img=x["image"]; last=img.split("@")[0].rsplit("/",1)[-1]
            tag=last.split(":",1)[1] if ":" in last else ""
            if tag in ("","latest","next","main","master","edge","stable","nightly","dev","develop") and "@sha256:" not in img:
                print(p["metadata"]["namespace"], img)'
```

On 2026-11-01 it listed only the democratic-csi pods. `dovah/muse` uses `latest` and is pinned by digest on purpose, because the upstream publishes no other tag. The scan skips an image with a digest.

## Evidence

- `apps/values.yaml`, the `tag:` lines of the 4 `democratic-csi-*` releases, each with a `# renovate:` comment.
- Image digests on 2026-11-01: running `latest` `sha256:944d0e65077efbd9c1fdf23997eec8fac4b4bfb7c3de400f63e33a0a849c5ced`, `v1.9.5` `sha256:fc3b7d7ed3a616714139525075312758e23a5d425ffb539ad12c9bd20fb6001f`, `next` `sha256:c6d74146e10b8ea2e0efd1f688779b6db529a71b83887ca3de953e5226d374b7`.
- The compare of `b5be00c...3974268` on GitHub: 3 commits, 1 file, `README.md`, 1 line added.
- [democratic-csi issue 509](https://github.com/democratic-csi/democratic-csi/issues/509), comments of the maintainer: [2025-10-31](https://github.com/democratic-csi/democratic-csi/issues/509#issuecomment-3474389761) (`next` supports 25.10 over REST) and [2026-10-06](https://github.com/democratic-csi/democratic-csi/issues/509#issuecomment-6019619601) (`next` supports TrueNAS 26 and later only, "support for ALL previous versions of TN has been dropped entirely").
- [layertwo/homelab pull request 2469](https://github.com/layertwo/homelab/pull/2469), merged 2026-10-10: the same pin, after provisioning stopped on TrueNAS 25.10.7.
