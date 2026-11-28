# A Renovate digest bump moved the Tuwunel pin off the CPU-optimised build

**Date:** 2026-11-28
**Component:** `matrix` Application, `deploy/tuwunel` image line, `renovate.json5`
**Severity:** none measured. The baseline pod did not become ready, so the downgrade served no traffic.

## Effect

The Renovate PR #737 changed the image reference of `deploy/tuwunel` from the x86-64-v3 platform manifest to the baseline amd64 manifest of the same `latest` index. The baseline build runs on the Intel N150 nodes. It gives up the CPU optimisation that the v3 pin exists for. No check in the cluster reported a difference: the same tag, the same code, a different manifest.

## Cause

The docker digest update of Renovate has no notion of CPU variants. For a multi-arch tag it proposes the index or the amd64 baseline manifest. It proposed `a2a37a8`, the baseline amd64 entry of the index that #736 pinned at `5e42c29e` (v3).

The tuwunel rule in `renovate.json5` worked as designed. The bump carried no `automerge` label, so a person had to merge it. The rule comment also names the procedure: re-pin to the v3 manifest of the new latest at merge time. The merge applied the proposed digest as it stood. The procedure came 1 bump too late.

## Correction

PR #738 re-pins the reference to the x86-64-v3 manifest `5e42c29e` of the current `latest` index. The image comment records the date and the PR number of the downgrade. The rule in `renovate.json5` now also adds `prBodyNotes`, so every future bump PR shows the re-pin step to the person who merges it. A merge that skips the step does so against a written instruction on the PR itself.

## Prevention

1. Read every tuwunel digest PR as a re-pin task, not a merge task. Replace the proposed digest with the v3 entry of the same index before merging.
2. Run the lookup in the PR body note of the renovate rule. It prints all amd64 variants of the current `latest`.
3. Apply the same care to every future Application that pins a variant of a multi-arch image. The failure is silent: no check is red, and the pod runs.

## Evidence

- `git show c79e719`: the image line moved to `sha256:a2a37a8` (baseline amd64).
- Image index of `ghcr.io/matrix-construct/tuwunel:latest`, read on 2026-11-28: arm64 `26e9b02`, amd64 baseline `a2a37a8`, amd64 v2 `67d6ab1`, amd64 v3 `5e42c29e`.
- `kubectl -n matrix get deploy tuwunel -o jsonpath='{.spec.template.spec.containers[0].image}'` after the merge of #737: the reference was the baseline digest.
- The baseline pod stayed on `CrashLoopBackOff` (see the legacy-port incident of the same day), so the downgrade cost no served traffic.
