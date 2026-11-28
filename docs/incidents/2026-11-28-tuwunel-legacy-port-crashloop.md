# The Tuwunel pod crash-looped on its first boot, on an env var the repository did not set

**Date:** 2026-11-28
**Component:** `matrix` Application, `deploy/tuwunel`, image digests `sha256:5e42c29e` and `sha256:a2a37a8`
**Severity:** the new stack had no service from the merge until PR #738 merged. No other Application and no data were at risk.

## Effect

The merge of #736 (11:11 UTC) created the namespace, both PVCs and both Deployments on the first sync. Both PVCs reached `Bound`. `deploy/tuwunel` then crash-looped on every start, so no homeserver endpoint existed. `deploy/heisenbridge` restarted behind it, because it could not reach its homeserver. Both public hosts answered with a proxy error.

## Cause

The container log of the previous start held the exact failure:

```text
Error: There was a problem with your configuration: data did not match any
variant of untagged enum Either for key "TUWUNEL_PORT" in environment
variable TUWUNEL_PORT (no configuration file was loaded; pass one with
--config or set TUWUNEL_CONFIG)
```

The image bakes the variable `TUWUNEL_PORT`, and the Deployment does not set it. The baked value is a list form. The current Tuwunel config parser accepts an integer or an array for the port, and it rejects the baked form. Startup stops at the first config read.

No CI check can catch this class of failure. Kubeconform validates the manifest schema. The env of the image is invisible in git, and no check boots the container.

## Correction

PR #738 sets `TUWUNEL_PORT: "8008"` in the Deployment env. A Deployment cannot remove an image-baked variable. It can only override it, so the override is the declarative fix. The value gives the parser an integer it accepts. It also matches the containerPort, the Service port and the documented default. The merge of PR #738 starts the pod, and the bridge settles behind it.

## Prevention

1. On a first boot that crash-loops, read the log of the previous start first. The error names the exact key.
2. Inspect `Config.Env` of a new image before a rollout, when the image moves its config format. The variables it bakes move with it.
3. Report the baked variable to upstream, so the image stops shipping a value its own parser rejects.

## Evidence

- Pod log, previous start, 2026-11-28 11:14 UTC: the error line quoted in Cause.
- `kubectl -n matrix get deploy tuwunel -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'` before the fix: the env list holds no `TUWUNEL_PORT`.
- `kubectl -n matrix get pvc`: both volumes `Bound` on the same sync, so storage was not part of the failure.
- The pod stayed on `CrashLoopBackOff` through the Renovate re-pin of #737, so the digest change did not touch the cause.
