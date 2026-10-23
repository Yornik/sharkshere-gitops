# The SMB proxy device joined the tailnet with the shared tag `tag:k8s`

**Date:** 2026-10-23
**Component:** `truenas-smb` Application, tailnet policy
**Severity:** not known. Tailnet Lock held the device after the merge. This file does not know whether it was signed since

## Effect

The first merge of `truenas-smb` made the Tailscale operator create the proxy device `nas-smb` with the default tag `tag:k8s`, because the Service set no tag. After a signature, each rule of the tailnet policy that gives access to `tag:k8s` would cover the SMB login of the NAS.

The jump hosts on the internet reach `gitlab-shell` over the tailnet. `gitlab-shell` has the same tag, so such a rule probably exists.

The first runbook also told the operator to sign the device first and fix the policy second. It told the operator to add a rule "to the device `nas-smb`". A tailnet policy rule cannot name a device.

## Cause

The default tag is `proxyConfig.defaultTags` in `apps/values.yaml`. The operator sets the tags of a proxy when it creates the proxy. It does not change them later, so a change of the annotation does not reach a device that exists.

## Correction

1. The Service sets `tailscale.com/tags: "tag:nas-smb"`.
2. In the tailnet policy: add `tag:nas-smb` to `tagOwners`, narrow each rule for all destinations, and add a rule for `tcp:445` from the PC to `tag:nas-smb`.
3. Replace the device that the first merge created. Remove the old device, delete the Service so that the operator creates a new proxy, check the tag, and sign last.

Steps 2 and 3 are actions on the tailnet and on the cluster that git cannot express. The steps are in [`../runbooks/truenas-smb.md`](../runbooks/truenas-smb.md).

## Prevention

1. Give a proxy that exposes a data service a tag of its own in the first merge.
2. Sign a new device last, after the policy and the NAS user are ready.
3. After the first signature, a change of tag needs a new proxy and a new signature.
4. Read the policy for a rule with a wildcard destination. The default policy of a tailnet is such a rule.

## Evidence

- `manifests/truenas-smb/service.yaml`, the annotation `tailscale.com/tags`.
- Tailscale operator v1.104.1, `cmd/k8s-operator/sts.go`: the auth key with the tags is created only when the proxy does not exist.
- `apps/values.yaml`, `proxyConfig.defaultTags` of `tailscale-operator`.
- `manifests/gitlab/service-ssh.yaml`: `gitlab-shell` has no tag annotation, so it has `tag:k8s`.
- 2 independent reviews of the merged change, on 2026-10-23.
